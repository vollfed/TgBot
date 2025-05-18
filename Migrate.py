# migrate_db.py
import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "user_messages.db"

def migrate():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE user_context ADD COLUMN continue_context BOOLEAN DEFAULT 0")
            print("✅ Migration complete.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("⚠️ Column 'continue_context' already exists.")
            else:
                raise

if __name__ == "__main__":
    migrate()