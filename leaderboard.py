from database import get_top_users,get_today_top

def make_leaderboard_text(rows):
    if not rows: return "🏆 अभी लीडरबोर्ड खाली है!"
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    text="🏆 *NEET Biology Top 10 Leaderboard* 🏆\n\n"
    for i,row in enumerate(rows):
        acc=(row["correct"]/row["attempted"]*100) if row["attempted"] else 0
        text+=f"{medals[i]} *{row['name']}* — {row['total_score']} अंक ({row['correct']}/{row['attempted']}) • {acc:.1f}% • 🔥 {row['streak']}\n"
    return text

def make_today_text(rows):
    if not rows: return "📊 आज अभी कोई score नहीं है।"
    return "📅 *Today's Top*\n\n" + "".join(f"{i}. *{r['name']}* — {r['total_score']} अंक\n" for i,r in enumerate(rows,1))
