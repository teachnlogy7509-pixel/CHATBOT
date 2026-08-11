from database import database


def get_top_users(limit=10):
    connection = database()
    rows = connection.execute("""
        SELECT name, total_score, correct, attempted
        FROM users
        ORDER BY total_score DESC, correct DESC
        LIMIT ?
    """, (limit,)).fetchall()
    connection.close()
    return rows


def make_leaderboard_text(rows):
    if not rows:
        return "🏆 अभी लीडरबोर्ड खाली है!"

    medals = [
        "🥇", "🥈", "🥉", "4️⃣", "5️⃣",
        "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"
    ]

    text = "🏆 *NEET Biology Top 10 Leaderboard* 🏆\n\n"

    for index, row in enumerate(rows):
        medal = medals[index] if index < len(medals) else f"{index + 1}."
        text += (
            f"{medal} *{row['name']}* — "
            f"{row['total_score']} अंक "
            f"({row['correct']}/{row['attempted']})\n"
        )

    return text
