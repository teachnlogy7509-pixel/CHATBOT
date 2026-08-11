import os
import google.generativeai as genai

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
)

from database import setup_database, get_poll, update_score, database
from quiz import send_poll_logic
from leaderboard import score_command_logic, leaderboard_command_logic

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ADMIN_IDS = {5874895507}
GEMINI_MODEL = "gemini-1.5-flash"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN missing")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

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
        "• /helpee - मदद",
        parse_mode="Markdown"
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() or "Cell Biology"
    await send_poll_logic(update, context, topic, "mcq")

async def assertion_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() or "Human Physiology"
    await send_poll_logic(update, context, topic, "assertion-reason")

async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll = get_poll(answer.poll_id)
    if not poll or not answer.option_ids:
        return

    selected = answer.option_ids[0]
    correct = selected == poll["correct_option"]
    points = 4 if correct else -1
    update_score(answer.user, points, correct)

    res_text = "✅ सही उत्तर! (+4 अंक)" if correct else "❌ गलत उत्तर! (-1 अंक)"
    try:
        await context.bot.send_message(
            chat_id=answer.user.id,
            text=f"{res_text}\n\n💡 व्याख्या: {poll['explanation']}"
        )
    except Exception:
        pass

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("💬 कृपया कुछ पूछें। उदाहरण: `/chatee Mitochondria kya hai?`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("🤖 Gemini सोच रहा है...")
    try:
        chat_resp = model.generate_content(f"आप NEET Biology AI Tutor हैं। छात्र के इस प्रश्न का हिंदी में सटीक उत्तर दें: {query}")
        await msg.edit_text(chat_resp.text)
    except Exception as e:
        print("Chat Error:", e)
        await msg.edit_text(f"❌ चैट करने में समस्या आई: {str(e)}")

async def motivation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mot_resp = model.generate_content("NEET aspirants के लिए एक पावरफुल मोटिवेशनल लाइन हिंदी में दें।")
        await update.message.reply_text(f"🔥 *Study Motivation*\n\n{mot_resp.text}", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("🔥 मेहनत इतनी खामोशी से करो कि सफलता शोर मचा दे!")

async def winner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ यह कमांड केवल एडमिन के लिए है।")
        return

    connection = database()
    rows = connection.execute("""
        SELECT name, total_score, correct FROM users
        ORDER BY total_score DESC, correct DESC
        LIMIT 3
    """).fetchall()
    connection.close()

    if not rows:
        await update.message.reply_text("🎉 अभी कोई विजेता उपलब्ध नहीं है!")
        return

    text = "🎉🎊 *NEET Test Top Winners Announcement* 🎊🎉\n\nशानदार प्रदर्शन करने वाले विनर्स:\n\n"
    medals = ["🥇 1st Winner", "🥈 2nd Winner", "🥉 3rd Winner"]
    for idx, row in enumerate(rows):
        text += f"{medals[idx]}\n👤 नाम: *{row['name']}*\n🏆 स्कोर: {row['total_score']} अंक (सही: {row['correct']})\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    setup_database()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("helpee", start_command))
    app.add_handler(CommandHandler("quizee", quiz))
    app.add_handler(CommandHandler("assertionee", assertion_reason))
    app.add_handler(CommandHandler("scoreee", score_command_logic))
    app.add_handler(CommandHandler("leaderboardee", leaderboard_command_logic))
    app.add_handler(CommandHandler("chatee", chat_command))
    app.add_handler(CommandHandler("motivationee", motivation_command))
    app.add_handler(CommandHandler("winneree", winner_command))
    app.add_handler(PollAnswerHandler(poll_answer))

    print("🚀 NEET Gemini Bot Started Successfully with Modular Structure!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
