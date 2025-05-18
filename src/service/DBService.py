import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "user_messages.db"
DB_PATH.parent.mkdir(exist_ok=True)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_context (
                user_id INTEGER PRIMARY KEY,
                transcript TEXT,
                title TEXT,
                language TEXT,
                continue_context BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()

#with sqlite3.connect(DB_PATH) as conn:
#    c = conn.cursor()
#    c.execute("ALTER TABLE user_context ADD COLUMN continue_context BOOLEAN DEFAULT 0")
#    conn.commit()

def store_message(user_id: int, text: str):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO user_messages (user_id, message) VALUES (?, ?)", (user_id, text))
        conn.commit()

def get_last_messages(user_id: int, limit=10):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT message FROM user_messages WHERE user_id=? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
        rows = c.fetchall()
        return [row[0] for row in reversed(rows)]  # Return in chronological order


def save_user_context(user_id: int, transcript=None, title=None, language=None, continue_context=None):
    current = get_user_context(user_id)

    transcript = transcript if transcript is not None else (current["transcript"] if current else None)
    title = title if title is not None else (current["title"] if current else None)
    language = language if language is not None else (current["language"] if current else None)
    continue_context = continue_context if continue_context is not None else (current["continue_context"] if current else 0)

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_context (user_id, transcript, title, language, continue_context)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                transcript=excluded.transcript,
                title=excluded.title,
                language=excluded.language,
                continue_context=excluded.continue_context
        """, (user_id, transcript, title, language, continue_context))
        conn.commit()



def get_user_context(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT transcript, title, language, continue_context FROM user_context WHERE user_id=?", (user_id,))
        row = c.fetchone()
    if row:
        return {
            "transcript": row[0],
            "title": row[1],
            "language": row[2],
            "continue_context": bool(row[3]),
        }
    else:
        return None

