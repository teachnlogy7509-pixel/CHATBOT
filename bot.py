import re
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from telegram.ext import ContextTypes,CommandHandler,MessageHandler,PollAnswerHandler,filters
from config import ADMIN_IDS
from database import (get_poll,get_pdfs,save_pdf,save_poll,save_schedule,get_schedules,delete_schedules,
save_user,update_score,reset_score,mark_poll_answer_once,save_mistake,get_mistakes,save_study_plan,
save_reminder,deactivate_reminder,set_viva_session,get_viva_session,clear_viva_session,
set_teach_session,get_teach_session,clear_teach_session,get_top_users,get_today_top)
from leaderboard import make_leaderboard_text,make_today_text
from quiz import ask_gemini,create_question
IST=ZoneInfo("Asia/Kolkata"); DEFAULT_POLL_TIMER=60

def parse_quiz_args(args):
    nums=[]
    while args and args[-1].isdigit(): nums.insert(0,int(args.pop()))
    if not args:return None,1,None
    if len(nums)==1:return " ".join(args),max(1,min(50,nums[0])),None
    return " ".join(args),max(1,min(50,nums[-2])),max(5,min(600,nums[-1]))

def parse_schedule_args(args):
    if len(args)<3:return None
    timer=None
    if args[-1].isdigit():timer=max(5,min(600,int(args.pop())))
    m=re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)",args.pop()) if args else None
    if not m or not args or not args[-1].isdigit():return None
    count=max(1,min(50,int(args.pop()))); topic=" ".join(args).strip()
    return (topic,count,int(m.group(1)),int(m.group(2)),timer) if topic else None

async def start_command(update, context):
    await update.message.reply_text(
        "🎯 *NEET Gemini Study Bot*\n\n"
        "📝 *Quiz*\n"
        "/quizee Biology 10\n"
        "/assertionee Genetics 5 60\n\n"
        "🏆 *Scores*\n"
        "/scoreee\n"
        "/leaderboardee\n"
        "/toptodayeeee\n"
        "/resetteetee\n"
        "/winneree\n\n"
        "🤖 *AI*\n"
        "/chatee <question>\n"
        "/motivationee\n"
        "/eli10eeee <topic>\n\n"
        "🧠 *Smart Study*\n"
        "/mistakeee\n"
        "/mistakequizeeee\n"
        "/teacheeee <topic>\n"
        "/vivaeeee <topic>\n"
        "/planeeee <topic> <days>\n"
        "/remindeeee <minutes> <text>\n"
        "/paniceeee <topic> <hours>\n"
        "/flashcardseeee <topic>\n"
        "/survivaleeee <topic>\n\n"
        "📄 *PDF*\n"
        "/pdfseeee\n\n"
        "⏰ *Admin Schedule*\n"
        "/scheduleeeee <topic> <count> HH:MM <timer>\n"
        "/unscheduleeeee\n\n"
        "🌅 Daily motivation and welcome messages are supported.",
        parse_mode="Markdown"
    )

async def quiz(update,context):
    args=list(context.args); topic,count,timer=parse_quiz_args(args)
    if not topic:return await update.message.reply_text("उदाहरण: /quizee Biology 10 60")
    for _ in range(count): await send_poll_logic(update,context,topic,"mcq",timer)

async def assertion_reason(update, context):
    args = list(context.args)
    topic, count, timer = parse_quiz_args(args)
    if not topic:
        await update.message.reply_text("उदाहरण: /assertionee Genetics 5 60")
        return
    for _ in range(count):
        await send_poll_logic(update, context, topic, "assertion-reason", timer)

async def send_poll_logic(update,context,topic,mode,timer=None):
    user,chat=update.effective_user,update.effective_chat; save_user(user)
    try:
        data=create_question(context.application.bot_data["gemini_client"],topic,mode)
        q_text=data["question"] if mode=="mcq" else f"कथन (A): {data['assertion']}\n\nकारण (R): {data['reason']}"
        kw={"chat_id":chat.id,"question":q_text[:300],"options":data["options"],"type":"quiz","is_anonymous":False,
            "correct_option_id":int(data["correct_option"]),"explanation":data["explanation"][:200]}
        if timer:kw["open_period"]=timer
        msg=await context.bot.send_poll(**kw)
        save_poll(msg.poll.id,chat.id,user.id,q_text,int(data["correct_option"]),data["explanation"])
    except Exception: await update.message.reply_text("❌ अभी Gemini से प्रश्न नहीं बन पाया।")

async def poll_answer(update,context):
    a=update.poll_answer; p=get_poll(a.poll_id)
    if not p or not a.option_ids or not mark_poll_answer_once(a.poll_id,a.user.id):return
    correct=a.option_ids[0]==p["correct_option"]
    update_score(a.user,4 if correct else -1,correct)
    if not correct:save_mistake(a.user.id,"Quiz",p["question"],f"Option {a.option_ids[0]+1}",f"Option {p['correct_option']+1}",p["explanation"])
    try:await context.bot.send_message(a.user.id,("✅ सही उत्तर! (+4 अंक)" if correct else "❌ गलत उत्तर! (-1 अंक)")+f"\n\n💡 {p['explanation']}")
    except Exception:pass

async def score_command(update,context):
    save_user(update.effective_user)
    from database import database
    c=database();r=c.execute("SELECT * FROM users WHERE user_id=?",(update.effective_user.id,)).fetchone();c.close()
    if not r:return await update.message.reply_text("पहले quiz attempt करें.")
    acc=r["correct"]/r["attempted"]*100 if r["attempted"] else 0
    await update.message.reply_text(f"📊 *आपका Score*\n🏆 अंक: {r['total_score']}\n📝 प्रयास: {r['attempted']}\n✅ सही: {r['correct']}\n🎯 Accuracy: {acc:.1f}%\n🔥 Streak: {r['streak']}\n⭐ XP: {r['xp']}",parse_mode="Markdown")

async def reset_command(update,context):
    reset_score(update.effective_user.id); await update.message.reply_text("🔄 Score, XP और mistakes reset हो गए।")

async def motivation_command(update, context):
    try:
        answer = ask_gemini(
            context.application.bot_data["gemini_client"],
            "NEET aspirants के लिए एक छोटी, positive और powerful motivational line हिंदी में दें।"
        )
    except Exception:
        answer = "मेहनत जारी रखो—हर दिन की छोटी progress तुम्हें goal के करीब ले जाती है! 💪"
    await update.message.reply_text(f"🔥 {answer}")

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

async def leaderboard_command(update,context):
    await update.message.reply_text(make_leaderboard_text(get_top_users(10)),parse_mode="Markdown")

async def today_command(update,context):
    await update.message.reply_text(make_today_text(get_today_top(10)),parse_mode="Markdown")

async def chat_command(update,context):
    q=" ".join(context.args).strip()
    if not q:return await update.message.reply_text("उदाहरण: /chatee mitochondria क्या है?")
    try:await update.message.reply_text(ask_gemini(context.application.bot_data["gemini_client"],f"NEET Biology tutor. हिंदी में उत्तर दें: {q}")[:4000])
    except Exception:await update.message.reply_text("❌ Gemini अभी उपलब्ध नहीं है।")

async def mistakes_command(update,context):
    rows=get_mistakes(update.effective_user.id,30)
    if not rows:return await update.message.reply_text("📕 अभी कोई mistake saved नहीं है।")
    text="📕 *Your Mistake Notebook*\n\n"
    for i,r in enumerate(rows,1):text+=f"{i}. *{r['topic']}*\n❓ {r['question'][:180]}\n✅ {r['correct_answer']}\n\n"
    await update.message.reply_text(text[:4000],parse_mode="Markdown")

async def mistake_quiz_command(update,context):
    rows=get_mistakes(update.effective_user.id,10)
    if not rows:return await update.message.reply_text("📕 पहले कुछ गलत answers होने चाहिए।")
    prompt="इन previous mistakes से 5 revision questions बनाओ:\n"+"\n".join(r["question"] for r in rows)
    try:await update.message.reply_text(ask_gemini(context.application.bot_data["gemini_client"],prompt)[:4000])
    except Exception:await update.message.reply_text("❌ Mistake quiz अभी उपलब्ध नहीं है।")

async def teach_command(update,context):
    topic=" ".join(context.args).strip()
    if not topic:return await update.message.reply_text("उदाहरण: /teachee Photosynthesis")
    set_teach_session(update.effective_user.id,update.effective_chat.id,topic)
    await update.message.reply_text(f"🧠 *Teach-Back*\n\n{topic} को अपने शब्दों में समझाओ।",parse_mode="Markdown")

async def viva_command(update,context):
    topic=" ".join(context.args).strip()
    if not topic:return await update.message.reply_text("उदाहरण: /vivaee Human Reproduction")
    q=ask_gemini(context.application.bot_data["gemini_client"],f"{topic} पर एक NEET viva question हिंदी में दो.")
    set_viva_session(update.effective_user.id,update.effective_chat.id,topic,q)
    await update.message.reply_text(f"🎤 *Viva Q1*\n\n{q}",parse_mode="Markdown")

async def plan_command(update,context):
    if len(context.args)<2:return await update.message.reply_text("उदाहरण: /planee Biology 30")
    days=int(context.args[-1]);topic=" ".join(context.args[:-1])
    try:
        plan=ask_gemini(context.application.bot_data["gemini_client"],f"{topic} के लिए {days} दिनों का NEET study roadmap हिंदी में बनाओ।")
        save_study_plan(update.effective_user.id,topic,days,plan);await update.message.reply_text(plan[:4000])
    except Exception:await update.message.reply_text("❌ Study plan अभी नहीं बन पाया।")

async def remind_command(update,context):
    if len(context.args)<2 or not context.args[0].isdigit():return await update.message.reply_text("उदाहरण: /remindee 30 Biology revise")
    mins=max(1,min(10080,int(context.args[0]))); text=" ".join(context.args[1:])
    rid=save_reminder(update.effective_user.id,update.effective_chat.id,text,datetime.utcnow().isoformat())
    context.job_queue.run_once(reminder_job,timedelta(minutes=mins),data={"id":rid,"chat_id":update.effective_chat.id,"text":text})
    await update.message.reply_text(f"⏰ Reminder set: {mins} minutes.")

async def reminder_job(context):
    d=context.job.data
    await context.bot.send_message(d["chat_id"],f"⏰ Reminder: {d['text']}")
    deactivate_reminder(d["id"])

async def eli10_command(update,context):
    topic=" ".join(context.args).strip()
    if not topic:return await update.message.reply_text("उदाहरण: /eli10ee Krebs Cycle")
    try:await update.message.reply_text(ask_gemini(context.application.bot_data["gemini_client"],f"{topic} को 10 साल के बच्चे जैसा आसान हिंदी में समझाओ.")[:4000])
    except Exception:await update.message.reply_text("❌ Explanation अभी उपलब्ध नहीं है।")

async def panic_command(update,context):
    if len(context.args)<2:return await update.message.reply_text("उदाहरण: /panicee Biology 2")
    hours=context.args[-1];topic=" ".join(context.args[:-1])
    try:await update.message.reply_text(ask_gemini(context.application.bot_data["gemini_client"],f"{hours} hours में {topic} का high-yield NEET revision plan हिंदी में बनाओ.")[:4000])
    except Exception:await update.message.reply_text("❌ Panic plan अभी उपलब्ध नहीं है।")

async def flashcards_command(update,context):
    topic=" ".join(context.args).strip()
    if not topic:return await update.message.reply_text("उदाहरण: /flashcardsee Cell")
    try:await update.message.reply_text(ask_gemini(context.application.bot_data["gemini_client"],f"{topic} के 10 NEET flashcards हिंदी में बनाओ. Q/A format.")[:4000])
    except Exception:await update.message.reply_text("❌ Flashcards अभी उपलब्ध नहीं हैं।")

async def survival_command(update,context):
    topic=" ".join(context.args).strip() or "Biology"
    await update.message.reply_text(f"🛡️ Survival Mode started!\nTopic: {topic}\nआगे normal quiz flow में questions भेजे जा सकते हैं।")

async def text_message(update,context):
    if update.effective_chat.type in ("group","supergroup") and not (update.message.reply_to_message and update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.id==context.bot.id):return
    text=(update.message.text or "").strip()
    if not text:return
    teach=get_teach_session(update.effective_user.id)
    if teach:
        try:
            ans=ask_gemini(context.application.bot_data["gemini_client"],f"Topic: {teach['topic']}\nStudent explanation: {text}\nEvaluate correct/missing/wrong concepts in Hindi.")
            clear_teach_session(update.effective_user.id);await update.message.reply_text(ans[:4000])
        except Exception:await update.message.reply_text("❌ Teach-Back evaluation unavailable.")
        return
    viva=get_viva_session(update.effective_user.id)
    if viva:
        try:
            ans=ask_gemini(context.application.bot_data["gemini_client"],f"Topic: {viva['topic']}\nQuestion: {viva['question']}\nStudent answer: {text}\nEvaluate then ask next question in Hindi.")
            set_viva_session(update.effective_user.id,update.effective_chat.id,viva["topic"],ans);await update.message.reply_text(ans[:4000])
        except Exception:await update.message.reply_text("❌ Viva evaluation unavailable.")
        return
    if not text.startswith("/"):
        try:await update.message.reply_text(ask_gemini(context.application.bot_data["gemini_client"],f"NEET Biology tutor. हिंदी में: {text}")[:4000])
        except Exception:pass

async def scheduled_quiz_job(context):
    d=context.job.data
    for _ in range(d["count"]):
        try:
            q=create_question(context.application.bot_data["gemini_client"],d["topic"],"mcq")
            kw={"chat_id":d["chat_id"],"question":q["question"][:300],"options":q["options"],"type":"quiz","is_anonymous":False,"correct_option_id":int(q["correct_option"]),"explanation":q["explanation"][:200]}
            if d["timer"]:kw["open_period"]=d["timer"]
            msg=await context.bot.send_poll(**kw);save_poll(msg.poll.id,d["chat_id"],d["admin_id"],q["question"],int(q["correct_option"]),q["explanation"])
        except Exception as exc:print("Scheduled quiz error:",exc)

async def morning_motivation_job(context):
    try:
        ans=ask_gemini(context.application.bot_data["gemini_client"],"NEET aspirants के लिए सुबह 2 lines का motivational message हिंदी में दो.")
    except Exception:ans="🔥 मेहनत जारी रखो—सफलता जरूर मिलेगी!"
    await context.bot.send_message(context.job.data["chat_id"],f"🌅 *Good Morning!*\n\n{ans}",parse_mode="Markdown")

async def welcome_new_members(update,context):
    if not update.message or not update.message.new_chat_members:return
    for m in update.message.new_chat_members:
        if not m.is_bot:await update.message.reply_text(f"🎉 Welcome *{m.first_name or m.full_name}*!\n📚 NEET Study Group में स्वागत है।",parse_mode="Markdown")

def add_schedule_job(app,row):
    app.job_queue.run_daily(scheduled_quiz_job,time=time(row["hour"],row["minute"],tzinfo=IST),data={"chat_id":row["chat_id"],"admin_id":row["admin_id"],"topic":row["topic"],"count":row["question_count"],"timer":row["timer_seconds"]},name=f"schedule_{row['id']}")

def add_motivation_job(app,chat_id):
    app.job_queue.run_daily(morning_motivation_job,time=time(7,0,tzinfo=IST),data={"chat_id":chat_id},name=f"motivation_{chat_id}")

async def schedule_command(update,context):
    if update.effective_user.id not in ADMIN_IDS:return update.message.reply_text("⚠️ केवल Admin.")
    parsed=parse_schedule_args(list(context.args))
    if not parsed:return update.message.reply_text("❌ Format: /scheduleee Biology 10 17:00 60")
    topic,count,hour,minute,timer=parsed;sid=save_schedule(update.effective_chat.id,update.effective_user.id,topic,count,hour,minute,timer)
    add_schedule_job(context.application,{"id":sid,"chat_id":update.effective_chat.id,"admin_id":update.effective_user.id,"topic":topic,"count":count,"question_count":count,"hour":hour,"minute":minute,"timer":timer,"timer_seconds":timer})
    add_motivation_job(context.application,update.effective_chat.id)
    return update.message.reply_text("✅ Daily schedule saved.",parse_mode="Markdown")

async def unschedule_command(update,context):
    if update.effective_user.id not in ADMIN_IDS:return update.message.reply_text("⚠️ केवल Admin.")
    delete_schedules(update.effective_chat.id,update.effective_user.id)
    for job in context.job_queue.jobs():
        if job.name.startswith("schedule_") and job.data.get("chat_id")==update.effective_chat.id:job.schedule_removal()
    return update.message.reply_text("✅ Daily schedule removed.")

def restore_schedules(app):
    for row in get_schedules():add_schedule_job(app,row)
    for row in get_schedules():add_motivation_job(app,row["chat_id"])

async def pdf_upload(update,context):
    user,doc=update.effective_user,update.effective_message.document
    if user.id not in ADMIN_IDS:return await update.message.reply_text("⚠️ PDF upload केवल Admin कर सकता है.")
    if not doc or not (doc.file_name or "").lower().endswith(".pdf"):return await update.message.reply_text("❌ केवल PDF भेजें.")
    save_pdf(doc.file_id,doc.file_name,user.id);await update.message.reply_text(f"✅ PDF सेव हो गई: {doc.file_name}")

async def pdfs_command(update,context):
    rows=get_pdfs()
    if not rows:return await update.message.reply_text("📚 अभी कोई PDF उपलब्ध नहीं है.")
    for row in rows:await context.bot.send_document(update.effective_chat.id,row["file_id"],caption=f"📄 {row['file_name']}")

def register_handlers(app):
    hs=[
      CommandHandler("startee",start_command),CommandHandler("helpee",start_command),
      CommandHandler("quizee",quiz),CommandHandler("assertionee",assertion_reason),CommandHandler("scoreee",score_command),
      CommandHandler("leaderboardee",leaderboard_command),CommandHandler("toptodayee",today_command),
      CommandHandler("resettee",reset_command),CommandHandler("chatee",chat_command),
      CommandHandler("motivationee",motivation_command),CommandHandler("winneree",winner_command),CommandHandler("mistakeee",mistakes_command),
      CommandHandler("mistakequizee",mistake_quiz_command),CommandHandler("teachee",teach_command),
      CommandHandler("vivaee",viva_command),CommandHandler("planee",plan_command),
      CommandHandler("remindee",remind_command),CommandHandler("eli10ee",eli10_command),
      CommandHandler("panicee",panic_command),CommandHandler("flashcardsee",flashcards_command),
      CommandHandler("survivalee",survival_command),CommandHandler("pdfsee",pdfs_command),
      CommandHandler("scheduleee",schedule_command),CommandHandler("unscheduleee",unschedule_command)
    ]
    for h in hs:app.add_handler(h)
    app.add_handler(PollAnswerHandler(poll_answer))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS,welcome_new_members))
    app.add_handler(MessageHandler(filters.Document.PDF,pdf_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_message))
