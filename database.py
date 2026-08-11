import sqlite3
from datetime import datetime, timezone

DB_FILE = "bot_data.db"


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
    """, (
        poll_id,
        chat_id,
        creator_id,
        question,
        correct_option,
        explanation,
        datetime.now(timezone.utc).isoformat(),
    ))
    connection.commit()
    connection.close()


def get_poll(poll_id):
    connection = database()
    row = connection.execute(
        "SELECT * FROM polls WHERE poll_id = ?", (poll_id,)
    ).fetchone()
    connection.close()
    return row


def save_pdf(file_id, file_name, uploaded_by):
    connection = database()
    connection.execute("""
        INSERT INTO pdfs (file_id, file_name, uploaded_by, uploaded_at)
        VALUES (?, ?, ?, ?)
    """, (
        file_id,
        file_name,
        uploaded_by,
        datetime.now(timezone.utc).isoformat(),
    ))
    connection.commit()
    connection.close()


def get_pdfs():
    connection = database()
    rows = connection.execute("""
        SELECT id, file_id, file_name, uploaded_at
        FROM pdfs
        ORDER BY id DESC
    """).fetchall()
    connection.close()
    return rows


def delete_pdf(pdf_id):
    connection = database()
    connection.execute("DELETE FROM pdfs WHERE id = ?", (pdf_id,))
    connection.commit()
    connection.close()
    return True
