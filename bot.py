import re
from datetime import time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, PollAnswerHandler, filters
)

from database import (
    get_poll, get_pdfs, save_pdf, save_poll, save_schedule, get_schedules,
    delete_schedules, save_user, update_score
)
from leaderboard import get_top_users, make_leaderboard_text
from quiz import ask_gemini, create_question

# अपना Telegram numeric User ID यहां रखें।
ADMIN_IDS = {5874895507}
IST = ZoneInfo("Asia/Kolkata")

# Defaults requested:
# Daily MCQ: 5:00 PM IST
# Morning motivation: 7:00 AM IST
DEFAULT_TOPIC = "Biology"
DEFAULT_QUESTION_COUNT = 10
DEFAULT_POLL_TIMER = 60  # 30 भी कर सकते हैं command में

def parse_quiz_args(args):
    nums = []
    while args and args[-1].isdigit():
        nums.insert(0, int(args.pop()))
    if not args:
        return None, 1, None
    if len(nums) == 1:
        return " ".join(args), max(1, min(50, nums[0])), None
    return " ".join(args), max(1, min(50, nums[-2])), max(5, min(600, nums[-1]))

def parse_schedule_args(args):
    if len(args) < 3:
        return None
    timer = None
    if args[-1].isdigit():
        timer = max(5, min(600, int(args.pop())))
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", args.pop()) if args else None
    if not match or not args or not args[-1].isdigit():
        return None
    count = max(1, min(50, int(args.pop())))
    topic = " ".join(args).strip()
    if not topic:
        return None
    return topic, count, int(match.group(1)), int(match.group(2)), timer

async def start_command(update, context):
    await update.message.reply_text(
        "🎯 *NEET Gemini Study Bot*\n\n"
        "📚 `/quizee Biology 10` → 10 MCQ\n"
        "⏱️ `/quizee Biology 10 60` → 10 MCQ, हर poll 60 सेकंड\n\n"
        "⏰ *Daily 5 PM MCQ Schedule:*\n"
        "`/schedule Biology 10 17:00 60`\n"
        "⏱️ Timer 30 या 60 सेकंड रख सकते हैं\n"
        "`/unschedule` → schedule हटाएं\n\n"
        "🌅 *Daily 7 AM Motivation:* अपने-आप group में आएगा\n"
        "👋 *New Member Welcome:* अपने-आप आएगा\n\n"
        "🏆 `/scoreee` • `/leaderboardee`\n"
        "💬 `/chatee सवाल` • 🔥 `/motivationee`\n"
        "📄 `/pdfs`",
        parse_mode="Markdown"
    )

async def quiz(update, context):
    args = list(context.args)
    topic, count, timer = parse_quiz_args(args)
    if not topic:
        await update.message.reply_text("उदाहरण: /quizee Biology 10 60")
        return
    await send_multiple_polls(update, context, topic, "mcq", count, timer)

async def assertion_reason(update, context):
    args = list(context.args)
    topic, count, timer = parse_quiz_args(args)
    if not topic:
        await update.message.reply_text("उदाहरण: /assertionee Genetics 5 60")
        return
    await send_multiple_polls(update, context, topic, "assertion-reason", count, timer)

async def send_multiple_polls(update, context, topic, mode, count, timer):
    status = await update.effective_message.reply_text(
        f"⏳ {topic} के {count} प्रश्न तैयार किए जा रहे हैं..."
    )
    for _ in range(count):
        await send_poll_logic(update, context, topic, mode, timer)
    try:
        await status.edit_text(f"✅ {count} प्रश्न भेज दिए गए!\n📚 Topic: {topic}")
    except Exception:
        pass

async def send_poll_logic(update, context, topic, mode, timer=None):
    user, chat = update.effective_user, update.effective_chat
    save_user(user)
    try:
        data = create_question(context.application.bot_data["gemini_client"], topic, mode)
        q_text = data["question"] if mode == "mcq" else (
            f"कथन (A): {data['assertion']}\n\nकारण (R): {data['reason']}"
        )
        kwargs = dict(
            chat_id=chat.id, question=q_text[:300], options=data["options"],
            type="quiz", is_anonymous=False,
            correct_option_id=int(data["correct_option"]),
            explanation=data["explanation"][:200]
        )
        if timer:
            kwargs["open_period"] = timer
        poll_msg = await context.bot.send_poll(**kwargs)
        save_poll(
            poll_msg.poll.id, chat.id, user.id, q_text,
            int(data["correct_option"]), data["explanation"]
        )
    except Exception as exc:
        print("Error creating question:", exc)
        await update.effective_message.reply_text(f"❌ प्रश्न बनाने में समस्या:\n{exc}")

async def poll_answer(update, context):
    answer = update.poll_answer
    poll = get_poll(answer.poll_id)
    if not poll or not answer.option_ids:
        return
    correct = answer.option_ids[0] == poll["correct_option"]
    update_score(answer.user, 4 if correct else -1, correct)
    text = "✅ सही उत्तर! (+4 अंक)" if correct else "❌ गलत उत्तर! (-1 अंक)"
    try:
        await context.bot.send_message(
            answer.user.id, f"{text}\n\n💡 {poll['explanation']}"
        )
    except Exception:
        pass

async def score_command(update, context):
    save_user(update.effective_user)
    from database import database
    con = database()
    row = con.execute(
        "SELECT * FROM users WHERE user_id=?", (update.effective_user.id,)
    ).fetchone()
    con.close()
    if not row:
        await update.message.reply_text("पहले कोई quiz attempt करें.")
        return
    accuracy = row["correct"] / row["attempted"] * 100 if row["attempted"] else 0
    await update.message.reply_text(
        f"📊 *आपका Score*\n\n👤 {row['name']}\n🏆 अंक: {row['total_score']}\n"
        f"📝 प्रयास: {row['attempted']}\n✅ सही: {row['correct']}\n🎯 Accuracy: {accuracy:.1f}%",
        parse_mode="Markdown"
    )

async def leaderboard_command(update, context):
    await update.message.reply_text(
        make_leaderboard_text(get_top_users(10)), parse_mode="Markdown"
    )

async def chat_command(update, context):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("उदाहरण: /chatee mitochondria क्या है?")
        return
    msg = await update.message.reply_text("🤖 Gemini सोच रहा है...")
    try:
        answer = ask_gemini(
            context.application.bot_data["gemini_client"],
            f"आप NEET Biology AI Tutor हैं। प्रश्न का हिंदी में सटीक उत्तर दें: {query}"
        )
        await msg.edit_text(answer)
    except Exception as exc:
        await msg.edit_text(f"❌ समस्या: {exc}")

async def motivation_command(update, context):
    try:
        answer = ask_gemini(
            context.application.bot_data["gemini_client"],
            "NEET aspirants के लिए एक छोटी motivational line हिंदी में दें।"
        )
        await update.message.reply_text(f"🔥 {answer}")
    except Exception:
        await update.message.reply_text("🔥 मेहनत जारी रखो—सफलता जरूर मिलेगी!")

async def winner_command(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ केवल Admin।")
        return
    rows = get_top_users(3)
    if not rows:
        await update.message.reply_text("अभी कोई winner नहीं है.")
        return
    medals = ["🥇", "🥈", "🥉"]
    text = "🎉 *Top 3 Winners* 🎉\n\n"
    for i, row in enumerate(rows):
        text += f"{medals[i]} *{row['name']}* — {row['total_score']} अंक\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def pdf_upload(update, context):
    user, doc = update.effective_user, update.effective_message.document
    if user.id not in ADMIN_IDS:
        await update.effective_message.reply_text("⚠️ PDF upload केवल Admin कर सकता है.")
        return
    if not doc or not (doc.file_name or "").lower().endswith(".pdf"):
        await update.effective_message.reply_text("❌ केवल PDF भेजें.")
        return
    save_pdf(doc.file_id, doc.file_name, user.id)
    await update.effective_message.reply_text(
        f"✅ PDF सेव हो गई!\n📄 {doc.file_name}\n\nयूज़र /pdfs से PDF पा सकते हैं."
    )

async def pdfs_command(update, context):
    rows = get_pdfs()
    if not rows:
        await update.message.reply_text("📚 अभी कोई PDF उपलब्ध नहीं है.")
        return
    for row in rows:
        await context.bot.send_document(
            update.effective_chat.id, row["file_id"], caption=f"📄 {row['file_name']}"
        )

async def scheduled_quiz_job(context):
    d = context.job.data
    for _ in range(d["count"]):
        try:
            q = create_question(
                context.application.bot_data["gemini_client"], d["topic"], "mcq"
            )
            kwargs = dict(
                chat_id=d["chat_id"], question=q["question"][:300], options=q["options"],
                type="quiz", is_anonymous=False,
                correct_option_id=int(q["correct_option"]),
                explanation=q["explanation"][:200]
            )
            if d["timer"]:
                kwargs["open_period"] = d["timer"]
            poll_msg = await context.bot.send_poll(**kwargs)
            save_poll(
                poll_msg.poll.id, d["chat_id"], d["admin_id"], q["question"],
                int(q["correct_option"]), q["explanation"]
            )
        except Exception as exc:
            print("Scheduled quiz error:", exc)

async def morning_motivation_job(context):
    d = context.job.data
    try:
        answer = ask_gemini(
            context.application.bot_data["gemini_client"],
            "NEET aspirants के लिए सुबह का एक छोटा, positive और powerful motivational message हिंदी में लिखें। 2-3 lines."
        )
        await context.bot.send_message(
            d["chat_id"], f"🌅 *Good Morning NEET Aspirants!*\n\n🔥 {answer}",
            parse_mode="Markdown"
        )
    except Exception as exc:
        print("Morning motivation error:", exc)

async def welcome_new_members(update, context):
    if not update.message or not update.message.new_chat_members:
        return
    chat_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        name = member.first_name or member.full_name
        await update.message.reply_text(
            f"🎉 Welcome *{name}*!\n\n"
            "📚 हमारे NEET Study Group में आपका स्वागत है।\n"
            "📝 Daily MCQ • 🏆 Leaderboard • 🔥 Motivation\n"
            "मेहनत शुरू रखिए और Best of Luck! 💪",
            parse_mode="Markdown"
        )

def add_schedule_job(app, row):
    app.job_queue.run_daily(
        scheduled_quiz_job,
        time=time(row["hour"], row["minute"], tzinfo=IST),
        data={
            "chat_id": row["chat_id"], "admin_id": row["admin_id"],
            "topic": row["topic"], "count": row["question_count"],
            "timer": row["timer_seconds"]
        },
        name=f"schedule_{row['id']}"
    )

def add_motivation_job(app, chat_id):
    # Unique per chat. Re-registering on restart is harmless because app is new.
    app.job_queue.run_daily(
        morning_motivation_job,
        time=time(7, 0, tzinfo=IST),
        data={"chat_id": chat_id},
        name=f"motivation_{chat_id}"
    )

async def schedule_command(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ केवल Admin.")
        return
    parsed = parse_schedule_args(list(context.args))
    if not parsed:
        await update.message.reply_text(
            "❌ सही format:\n/schedule Biology 10 17:00 60\n\n"
            "5 PM = 17:00\nTimer 30 या 60 सेकंड रख सकते हैं."
        )
        return
    topic, count, hour, minute, timer = parsed
    sid = save_schedule(
        update.effective_chat.id, update.effective_user.id,
        topic, count, hour, minute, timer
    )
    add_schedule_job(context.application, {
        "id": sid, "chat_id": update.effective_chat.id,
        "admin_id": update.effective_user.id, "topic": topic,
        "question_count": count, "hour": hour, "minute": minute,
        "timer_seconds": timer
    })
    # Also ensure 7 AM motivation is enabled for this chat.
    add_motivation_job(context.application, update.effective_chat.id)
    await update.message.reply_text(
        f"✅ *Daily MCQ Schedule लग गया!*\n\n"
        f"📚 Topic: {topic}\n📝 Questions: {count}\n"
        f"⏰ Time: {hour:02d}:{minute:02d} IST\n"
        f"⏱️ Timer: {timer or 60} सेकंड\n\n"
        "🌅 7:00 AM daily motivation भी ON है.",
        parse_mode="Markdown"
    )

async def unschedule_command(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ केवल Admin.")
        return
    delete_schedules(update.effective_chat.id, update.effective_user.id)
    for job in context.job_queue.jobs():
        if job.name.startswith("schedule_") and job.data.get("chat_id") == update.effective_chat.id:
            job.schedule_removal()
    await update.message.reply_text(
        "✅ इस chat का daily MCQ schedule हटा दिया गया.\n"
        "🌅 7 AM motivation और welcome feature चालू रहेंगे."
    )

def restore_schedules(app):
    rows = get_schedules()
    chat_ids = set()
    for row in rows:
        add_schedule_job(app, row)
        chat_ids.add(row["chat_id"])
    # Every saved scheduled chat gets 7 AM motivation.
    for chat_id in chat_ids:
        add_motivation_job(app, chat_id)

def register_handlers(app):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("quizee", quiz))
    app.add_handler(CommandHandler("assertionee", assertion_reason))
    app.add_handler(CommandHandler("scoreee", score_command))
    app.add_handler(CommandHandler("leaderboardee", leaderboard_command))
    app.add_handler(CommandHandler("chatee", chat_command))
    app.add_handler(CommandHandler("motivationee", motivation_command))
    app.add_handler(CommandHandler("winneree", winner_command))
    app.add_handler(CommandHandler("pdfs", pdfs_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("unschedule", unschedule_command))
    app.add_handler(PollAnswerHandler(poll_answer))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_upload))
