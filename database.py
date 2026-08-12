import sqlite3
from datetime import datetime, timezone
from config import DB_FILE

def database():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def setup_database():
    c = database()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT,
      total_score INTEGER DEFAULT 0, attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0,
      streak INTEGER DEFAULT 0, last_study_date TEXT, xp INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS polls(
      poll_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, creator_id INTEGER NOT NULL,
      question TEXT NOT NULL, correct_option INTEGER NOT NULL, explanation TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS poll_answers(
      poll_id TEXT NOT NULL, user_id INTEGER NOT NULL, answered_at TEXT NOT NULL,
      PRIMARY KEY(poll_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS pdfs(
      id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL, file_name TEXT NOT NULL,
      uploaded_by INTEGER NOT NULL, uploaded_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS schedules(
      id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, admin_id INTEGER NOT NULL,
      topic TEXT NOT NULL, question_count INTEGER NOT NULL, hour INTEGER NOT NULL,
      minute INTEGER NOT NULL, timer_seconds INTEGER, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS mistakes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, topic TEXT NOT NULL,
      question TEXT NOT NULL, selected_answer TEXT, correct_answer TEXT NOT NULL,
      explanation TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS study_plans(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, topic TEXT NOT NULL,
      days INTEGER NOT NULL, plan_text TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reminders(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
      text TEXT NOT NULL, run_at TEXT NOT NULL, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS viva_sessions(
      user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, topic TEXT NOT NULL,
      question TEXT, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS teach_sessions(
      user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, topic TEXT NOT NULL,
      active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS achievements(
      user_id INTEGER NOT NULL, badge TEXT NOT NULL, earned_at TEXT NOT NULL,
      PRIMARY KEY(user_id,badge)
    );
    CREATE TABLE IF NOT EXISTS survival_records(
      user_id INTEGER PRIMARY KEY, topic TEXT NOT NULL, best_streak INTEGER DEFAULT 0,
      updated_at TEXT NOT NULL
    );
    """)
    c.commit(); c.close()

def save_user(user):
    c=database()
    c.execute("""INSERT INTO users(user_id,name,username) VALUES(?,?,?)
      ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username""",
      (user.id,user.full_name,user.username))
    c.commit(); c.close()

def update_score(user, points, was_correct):
    save_user(user); c=database(); today=datetime.now(timezone.utc).date().isoformat()
    row=c.execute("SELECT streak,last_study_date,xp FROM users WHERE user_id=?",(user.id,)).fetchone()
    streak=(row["streak"] if row else 0)
    last=(row["last_study_date"] if row else None)
    if last!=today: streak=streak+1 if last else 1
    c.execute("""UPDATE users SET total_score=total_score+?, attempted=attempted+1,
      correct=correct+?, streak=?, last_study_date=?, xp=xp+? WHERE user_id=?""",
      (points,1 if was_correct else 0,streak,today,10 if was_correct else 0,user.id))
    c.commit(); c.close()

def reset_score(user_id):
    c=database(); c.execute("""UPDATE users SET total_score=0,attempted=0,correct=0,streak=0,xp=0 WHERE user_id=?""",(user_id,))
    c.execute("DELETE FROM mistakes WHERE user_id=?",(user_id,))
    c.commit(); c.close()

def save_poll(poll_id,chat_id,creator_id,question,correct_option,explanation):
    c=database(); c.execute("""INSERT OR REPLACE INTO polls
      (poll_id,chat_id,creator_id,question,correct_option,explanation,created_at)
      VALUES(?,?,?,?,?,?,?)""",(str(poll_id),chat_id,creator_id,question,correct_option,explanation,datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()

def get_poll(poll_id):
    c=database(); row=c.execute("SELECT * FROM polls WHERE poll_id=?",(str(poll_id),)).fetchone(); c.close(); return row

def mark_poll_answer_once(poll_id,user_id):
    c=database()
    try:
        c.execute("INSERT INTO poll_answers VALUES(?,?,?)",(str(poll_id),user_id,datetime.now(timezone.utc).isoformat()))
        c.commit(); ok=True
    except sqlite3.IntegrityError: ok=False
    c.close(); return ok

def save_mistake(user_id,topic,question,selected_answer,correct_answer,explanation):
    c=database(); c.execute("""INSERT INTO mistakes
      (user_id,topic,question,selected_answer,correct_answer,explanation,created_at)
      VALUES(?,?,?,?,?,?,?)""",(user_id,topic,question,selected_answer,correct_answer,explanation,datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()

def get_mistakes(user_id,limit=50):
    c=database(); rows=c.execute("SELECT * FROM mistakes WHERE user_id=? ORDER BY id DESC LIMIT ?",(user_id,limit)).fetchall(); c.close(); return rows

def save_pdf(file_id,file_name,uploaded_by):
    c=database(); c.execute("INSERT INTO pdfs(file_id,file_name,uploaded_by,uploaded_at) VALUES(?,?,?,?)",(file_id,file_name,uploaded_by,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()

def get_pdfs():
    c=database(); rows=c.execute("SELECT * FROM pdfs ORDER BY id DESC").fetchall(); c.close(); return rows

def save_schedule(chat_id,admin_id,topic,count,hour,minute,timer):
    c=database(); cur=c.execute("""INSERT INTO schedules(chat_id,admin_id,topic,question_count,hour,minute,timer_seconds,created_at)
      VALUES(?,?,?,?,?,?,?,?)""",(chat_id,admin_id,topic,count,hour,minute,timer,datetime.now(timezone.utc).isoformat())); c.commit(); sid=cur.lastrowid; c.close(); return sid

def get_schedules():
    c=database(); rows=c.execute("SELECT * FROM schedules ORDER BY id").fetchall(); c.close(); return rows

def delete_schedules(chat_id,admin_id):
    c=database(); c.execute("DELETE FROM schedules WHERE chat_id=? AND admin_id=?",(chat_id,admin_id)); c.commit(); c.close()

def get_top_users(limit=10):
    c=database(); rows=c.execute("""SELECT name,total_score,correct,attempted,streak,xp FROM users
      WHERE attempted>0 ORDER BY total_score DESC,correct DESC LIMIT ?""",(limit,)).fetchall(); c.close(); return rows

def get_today_top(limit=10):
    return get_top_users(limit)

def save_study_plan(user_id,topic,days,plan_text):
    c=database(); c.execute("INSERT INTO study_plans(user_id,topic,days,plan_text,created_at) VALUES(?,?,?,?,?)",(user_id,topic,days,plan_text,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()

def save_reminder(user_id,chat_id,text,run_at):
    c=database(); cur=c.execute("INSERT INTO reminders(user_id,chat_id,text,run_at,active) VALUES(?,?,?,?,1)",(user_id,chat_id,text,run_at)); c.commit(); rid=cur.lastrowid; c.close(); return rid

def get_active_reminders():
    c=database(); rows=c.execute("SELECT * FROM reminders WHERE active=1 ORDER BY run_at").fetchall(); c.close(); return rows

def deactivate_reminder(reminder_id):
    c=database(); c.execute("UPDATE reminders SET active=0 WHERE id=?",(reminder_id,)); c.commit(); c.close()

def set_viva_session(user_id,chat_id,topic,question):
    c=database(); c.execute("""INSERT INTO viva_sessions VALUES(?,?,?,?,1)
      ON CONFLICT(user_id) DO UPDATE SET chat_id=excluded.chat_id,topic=excluded.topic,question=excluded.question,active=1""",(user_id,chat_id,topic,question)); c.commit(); c.close()

def get_viva_session(user_id):
    c=database(); row=c.execute("SELECT * FROM viva_sessions WHERE user_id=? AND active=1",(user_id,)).fetchone(); c.close(); return row

def clear_viva_session(user_id):
    c=database(); c.execute("DELETE FROM viva_sessions WHERE user_id=?",(user_id,)); c.commit(); c.close()

def set_teach_session(user_id,chat_id,topic):
    c=database(); c.execute("""INSERT INTO teach_sessions VALUES(?,?,?,1)
      ON CONFLICT(user_id) DO UPDATE SET chat_id=excluded.chat_id,topic=excluded.topic,active=1""",(user_id,chat_id,topic)); c.commit(); c.close()

def get_teach_session(user_id):
    c=database(); row=c.execute("SELECT * FROM teach_sessions WHERE user_id=? AND active=1",(user_id,)).fetchone(); c.close(); return row

def clear_teach_session(user_id):
    c=database(); c.execute("DELETE FROM teach_sessions WHERE user_id=?",(user_id,)); c.commit(); c.close()
