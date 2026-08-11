import os

from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    PollAnswerHandler,
    filters,
)

from database import (
    get_poll,
    get_pdfs,
    save_pdf,
    save_poll,
    save_user,
    update_score,
)
from leaderboard import get_top_users, make_leaderboard_text
from quiz import ask_gemini, create_question


ADMIN_IDS = {5874895507}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 *नमस्ते! NEET Gemini Study Bot में आपका स्वागत है।*\n\n"
        "📖 उपलब्ध कमांड्स:\n"
        "• /quizee [topic] - MCQ क्विज़ पोल\n"
        "• /assertionee [topic] - Assertion-Reason पोल\n"
        "• /scoreee - अपना स्कोर देखें\n"
        "• /leaderboardee - टॉप 10 लीडरबोर्ड\n"
        "• /chatee [सवाल] - Gemini से चैट करें\n"
        "• /motivationee - मोटिवेशन लाइन\n"
        "• /winneree - (Admin) विनर्स घोषणा\n"
        "• /pdfs - उपलब्ध PDFs\n"
        "• Admin सीधे PDF भेजकर उसे सेव कर सकता है\n"
        "• /helpee - मदद",
        parse_mode="Markdown",
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() or "Cell Biology"
    await send_poll_logic(update, context, topic, "mcq")


async def assertion_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() or "Human Physiology"
    await send_poll_logic(update, context, topic, "assertion-reason")


async def send_poll_logic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
    mode: str,
):
    user = update.effective_user
    chat = update.effective_chat
    save_user(user)

    waiting_msg = await update.effective_message.reply_text(
        f"⏳ {topic} पर NEET प्रश्न तैयार हो रहा है..."
    )

    try:
        client = context.application.bot_data["gemini_client"]
        data = create_question(client, topic, mode)

        if mode == "mcq":
            q_text = data["question"]
        else:
            q_text = (
                f"कथन (A): {data['assertion']}\n\n"
                f"कारण (R): {data['reason']}"
            )

        poll_msg = await context.bot.send_poll(
            chat_id=chat.id,
            question=q_text,
            options=data["options"],
            type="quiz",
            is_anonymous=False,
            correct_option_id=int(data["correct_option"]),
            explanation=data["explanation"],
        )

        save_poll(
            poll_id=poll_msg.poll.id,
            chat_id=chat.id,
            creator_id=user.id,
            question=q_text,
            correct_option=int(data["correct_option"]),
            explanation=data["explanation"],
        )

        await waiting_msg.delete()

    except Exception as exc:
        print("Error creating question:", exc)
        await waiting_msg.edit_text(
            f"❌ प्रश्न बनाने में त्रुटि हुई:\n{exc}"
        )


async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll = get_poll(answer.poll_id)

    if not poll or not answer.option_ids:
        return

    selected = answer.option_ids[0]
    correct = selected == poll["correct_option"]
    points = 4 if correct else -1

    update_score(answer.user, points, correct)

    result_text = (
        "✅ सही उत्तर! (+4 अंक)"
        if correct
        else "❌ गलत उत्तर! (-1 अंक)"
    )

    try:
        await context.bot.send_message(
            chat_id=answer.user.id,
            text=f"{result_text}\n\n💡 व्याख्या: {poll['explanation']}",
        )
    except Exception:
        pass


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    from database import database

    connection = database()
    row = connection.execute(
        "SELECT * FROM users WHERE user_id = ?", (user.id,)
    ).fetchone()
    connection.close()

    if not row:
        await update.message.reply_text(
            "आपका कोई रिकॉर्ड नहीं मिला। पहले क्विज़ खेलें!"
        )
        return

    accuracy = (
        row["correct"] / row["attempted"] * 100
        if row["attempted"] > 0
        else 0
    )

    await update.message.reply_text(
        f"📊 *आपका स्कोर कार्ड*\n\n"
        f"👤 नाम: {row['name']}\n"
        f"🏆 कुल अंक: {row['total_score']}\n"
        f"📝 कुल प्रयास: {row['attempted']}\n"
        f"✅ सही उत्तर: {row['correct']}\n"
        f"🎯 सटीकता: {accuracy:.1f}%",
        parse_mode="Markdown",
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_top_users(10)
    await update.message.reply_text(
        make_leaderboard_text(rows),
        parse_mode="Markdown",
    )


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()

    if not query:
        await update.message.reply_text(
            "💬 कृपया कुछ पूछें। उदाहरण: "
            "`/chatee Mitochondria kya hai?`",
            parse_mode="Markdown",
        )
        return

    msg = await update.message.reply_text("🤖 Gemini सोच रहा है...")

    try:
        client = context.application.bot_data["gemini_client"]
        answer = ask_gemini(
            client,
            "आप NEET Biology AI Tutor हैं। "
            f"छात्र के इस प्रश्न का हिंदी में सटीक उत्तर दें: {query}",
        )
        await msg.edit_text(answer)

    except Exception as exc:
        print("Chat Error:", exc)
        await msg.edit_text(f"❌ चैट करने में समस्या आई:\n{exc}")


async def motivation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        client = context.application.bot_data["gemini_client"]
        answer = ask_gemini(
            client,
            "NEET aspirants के लिए एक पावरफुल motivational line "
            "हिंदी में दें।",
        )
        await update.message.reply_text(
            f"🔥 *Study Motivation*\n\n{answer}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        print("Motivation Error:", exc)
        await update.message.reply_text(
            "🔥 मेहनत इतनी खामोशी से करो कि सफलता शोर मचा दे!"
        )


async def winner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "⚠️ यह कमांड केवल एडमिन के लिए है।"
        )
        return

    rows = get_top_users(3)

    if not rows:
        await update.message.reply_text(
            "🎉 अभी कोई विजेता उपलब्ध नहीं है!"
        )
        return

    medals = ["🥇 1st Winner", "🥈 2nd Winner", "🥉 3rd Winner"]
    text = (
        "🎉🎊 *NEET Test Top Winners Announcement* 🎊🎉\n\n"
        "शानदार प्रदर्शन करने वाले विनर्स:\n\n"
    )

    for index, row in enumerate(rows):
        text += (
            f"{medals[index]}\n"
            f"👤 नाम: *{row['name']}*\n"
            f"🏆 स्कोर: {row['total_score']} अंक "
            f"(सही: {row['correct']})\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


async def pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message

    if not user or user.id not in ADMIN_IDS:
        await message.reply_text(
            "⚠️ PDF अपलोड करने की अनुमति केवल Admin को है।"
        )
        return

    document = message.document
    if not document:
        return

    file_name = document.file_name or "document.pdf"

    if not file_name.lower().endswith(".pdf"):
        await message.reply_text("❌ केवल PDF फाइल अपलोड करें।")
        return

    save_pdf(document.file_id, file_name, user.id)

    await message.reply_text(
        f"✅ PDF सेव हो गई!\n\n"
        f"📄 {file_name}\n\n"
        "यूज़र /pdfs कमांड से उपलब्ध PDFs पा सकते हैं।"
    )


async def pdfs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_pdfs()

    if not rows:
        await update.message.reply_text(
            "📚 अभी कोई PDF उपलब्ध नहीं है।"
        )
        return

    for row in rows:
        try:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=row["file_id"],
                caption=f"📄 {row['file_name']}",
            )
        except Exception as exc:
            print(f"PDF send error: {exc}")


async def unknown_pdf_or_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📄 PDF भेजनी है तो केवल Admin PDF upload कर सकता है।"
    )


def register_handlers(app):
    from telegram.ext import (
        CommandHandler,
        MessageHandler,
        PollAnswerHandler,
        filters,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("helpee", start_command))
    app.add_handler(CommandHandler("quizee", quiz))
    app.add_handler(CommandHandler("assertionee", assertion_reason))
    app.add_handler(CommandHandler("scoreee", score_command))
    app.add_handler(CommandHandler("leaderboardee", leaderboard_command))
    app.add_handler(CommandHandler("chatee", chat_command))
    app.add_handler(CommandHandler("motivationee", motivation_command))
    app.add_handler(CommandHandler("winneree", winner_command))
    app.add_handler(CommandHandler("pdfs", pdfs_command))

    app.add_handler(PollAnswerHandler(poll_answer))

    # PDF handler runs only for PDF documents.
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_upload))
