from database import database

async def score_command_logic(update, context):
    user = update.effective_user
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

async def leaderboard_command_logic(update, context):
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
