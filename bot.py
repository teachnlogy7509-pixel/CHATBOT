import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
    MessageHandler,
    filters,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ADMIN_IDS = {5874895507}
DB_FILE = "bot_data.db"
GEMINI_MODEL = "gemini-2.5-flash"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN missing")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

def database():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection

def setup_database():
    connection = database()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT,
            total_score INTEGER DEFAULT 0,
            attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS polls (
            poll_id TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            correct_option INTEGER NOT NULL,
            explanation TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS pdfs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    """)
    connection.commit()
    connection.close()

def save_user(user):
    connection = database()
    connection.execute("""
        INSERT INTO users (user_id, name, username)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            username = excluded.username
    """, (user.id, user.full_name, user.username))
    connection.commit()
    connection.close()

def update_score(user, points, was_correct):
    save_user(user)
    connection = database()
    connection.execute("""
        UPDATE users
        SET total_score = total_score + ?,
            attempted = attempted + 1,
            correct = correct + ?
        WHERE user_id = ?
    """, (points, 1 if was_correct else 0, user.id))
    connection.commit()
    connection.close()

def save_poll(poll_id, chat_id, creator_id, question, correct_option, explanation):
    connection = database()
    connection.execute("""
        INSERT OR REPLACE INTO polls
        (poll_id, chat_id, creator_id, question, correct_option, explanation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (poll_id, chat_id, creator_id, question, correct_option, explanation, datetime.now(timezone.utc).isoformat()))
    connection.commit()
    connection.close()

def get_poll(poll_id):
    connection = database()
    row = connection.execute("SELECT * FROM polls WHERE poll_id = ?", (poll_id,)).fetchone()
    connection.close()
    return row

def save_pdf(file_id: str, file_name: str, uploaded_by: int):
    connection = database()
    connection.execute(
        "INSERT INTO pdfs (file_id, file_name, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?)",
        (file_id, file_name, uploaded_by, datetime.now(timezone.utc).isoformat())
    )
    connection.commit()
    connection.close()


def get_pdfs():
    connection = database()
    rows = connection.execute(
        "SELECT id, file_id, file_name FROM pdfs ORDER BY id DESC"
    ).fetchall()
    connection.close()
    return rows


async def pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message

    if not user or user.id not in ADMIN_IDS:
        await message.reply_text("⚠️ PDF अपलोड करने की अनुमति केवल Admin को है।")
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
        f"✅ PDF सेव हो गई!\n\n📄 {file_name}\n\n"
        "यूज़र /pdfs कमांड से उपलब्ध PDFs देख सकते हैं।"
    )


async def pdfs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_pdfs()

    if not rows:
        await update.message.reply_text("📚 अभी कोई PDF उपलब्ध नहीं है।")
        return

    for row in rows:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=row["file_id"],
            caption=f"📄 {row['file_name']}"
        )


async def create_question(topic: str, mode: str) -> dict[str, Any]:
    if mode == "mcq":
        instructions = "यह एक सामान्य NEET Biology MCQ होना चाहिए। 'question' में प्रश्न लिखें।"
    else:
        instructions = "यह Assertion-Reason question होना चाहिए। 'assertion' और 'reason' लिखें।"

    prompt = f"""
आप NEET Biology के expert teacher हैं।
Topic: {topic}
Question type: {mode}
इस topic पर NCERT लेवल का एक नया हिंदी प्रश्न बनाएं।
उत्तर केवल JSON format में दें जिसमें ये keys हों: question, assertion, reason, options (4 items की list), correct_option (0 से 3 के बीच integer), explanation।
"""

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )

    data = json.loads(response.text)
    if len(data.get("options", [])) != 4:
        raise ValueError("Gemini ने 4 options नहीं दिए")
    return data

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
        "• Admin PDF भेजकर उसे सेव कर सकता है\n"
        "• /helpee - मदद",
        parse_mode="Markdown"
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() or "Cell Biology"
    await send_poll_logic(update, context, topic, "mcq")

async def assertion_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() or "Human Physiology"
    await send_poll_logic(update, context, topic, "assertion-reason")

async def send_poll_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, mode: str):
    user = update.effective_user
    chat = update.effective_chat
    save_user(user)

    waiting_msg = await update.effective_message.reply_text(f"⏳ {topic} पर NEET प्रश्न तैयार हो रहा है...")

    try:
        data = await create_question(topic, mode)
        q_text = data.get("question") if mode == "mcq" else f"कथन (A): {data.get('assertion')}\n\nकारण (R): {data.get('reason')}"

        poll_msg = await context.bot.send_poll(
            chat_id=chat.id,
            question=q_text,
            options=data["options"],
            type="quiz",
            is_anonymous=False,
            correct_option_id=int(data["correct_option"]),
            explanation=data["explanation"]
        )

        save_poll(
            poll_id=poll_msg.poll.id,
            chat_id=chat.id,
            creator_id=user.id,
            question=q_text,
            correct_option=int(data["correct_option"]),
            explanation=data["explanation"]
        )
        await waiting_msg.delete()
    except Exception as e:
        print("Error creating question:", e)
        await waiting_msg.edit_text(f"❌ प्रश्न बनाने में त्रुटि हुई: {str(e)}")

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

async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)
    connection = database()
    row = connection.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone()
    connection.close()

    if not row:
        await update.message.reply_text("आपका कोई रिकॉर्ड नहीं मिला। पहले क्विज़ खेलें!")
        return

    accuracy = (row["correct"] / row["attempted"] * 100) if row["attempted"] > 0 else 0
    await update.message.reply_text(
        f"📊 *आपका स्कोर कार्ड*\n\n"
        f"👤 नाम: {row['name']}\n"
        f"🏆 कुल अंक: {row['total_score']}\n"
        f"📝 कुल प्रयास: {row['attempted']}\n"
        f"✅ सही उत्तर: {row['correct']}\n"
        f"🎯 सटीकता: {accuracy:.1f}%",
        parse_mode="Markdown"
    )

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    connection = database()
    rows = connection.execute("""
        SELECT name, total_score, correct, attempted
        FROM users
        ORDER BY total_score DESC, correct DESC
        LIMIT 10
    """).fetchall()
    connection.close()

    if not rows:
        await update.message.reply_text("🏆 अभी लीडरबोर्ड खाली है!")
        return

    text = "🏆 *NEET Biology Top 10 Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, row in enumerate(rows):
        medal = medals[idx] if idx < 10 else f"{idx+1}."
        text += f"{medal} *{row['name']}* — {row['total_score']} अंक ({row['correct']}/{row['attempted']})\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("💬 कृपया कुछ पूछें। उदाहरण: `/chatee Mitochondria kya hai?`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("🤖 Gemini सोच रहा है...")
    try:
        chat_resp = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"आप NEET Biology AI Tutor हैं। छात्र के इस प्रश्न का हिंदी में सटीक उत्तर दें: {query}"
        )
        await msg.edit_text(chat_resp.text)
    except Exception as e:
        print("Chat Error:", e)
        await msg.edit_text(f"❌ चैट करने में समस्या आई: {str(e)}")

async def motivation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mot_resp = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents="NEET aspirants के लिए एक पावरफुल मोटिवेशनल लाइन हिंदी में दें।"
        )
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
    app.add_handler(CommandHandler("scoreee", score_command))
    app.add_handler(CommandHandler("leaderboardee", leaderboard_command))
    app.add_handler(CommandHandler("chatee", chat_command))
    app.add_handler(CommandHandler("motivationee", motivation_command))
    app.add_handler(CommandHandler("winneree", winner_command))
    app.add_handler(CommandHandler("pdfs", pdfs_command))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_upload))
    app.add_handler(PollAnswerHandler(poll_answer))

    print("🚀 NEET Gemini Bot Started Successfully!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
