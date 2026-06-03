import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Create processed messages table to avoid double-reacting
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create reaction logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sender_username TEXT,
                thread_title TEXT,
                message_text TEXT,
                reaction_emoji TEXT,
                reel_url TEXT
            )
        """)
        conn.commit()

def get_setting(key: str, default: str = None) -> str:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default
    except Exception:
        return default

def save_setting(key: str, value: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def get_all_settings():
    settings = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            for row in rows:
                settings[row["key"]] = row["value"]
    except Exception:
        pass
    return settings

def is_message_processed(message_id: str) -> bool:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,))
            return cursor.fetchone() is not None
    except Exception:
        return False

def mark_message_processed(message_id: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)", (message_id,))
            conn.commit()
    except Exception:
        pass

def add_log(sender_username: str, thread_title: str, message_text: str, reaction_emoji: str, reel_url: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reaction_logs (sender_username, thread_title, message_text, reaction_emoji, reel_url)
                VALUES (?, ?, ?, ?, ?)
            """, (sender_username, thread_title, message_text, reaction_emoji, reel_url))
            conn.commit()
    except Exception as e:
        print(f"Error adding log: {e}")

def get_logs(limit: int = 100):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, datetime(timestamp, 'localtime') as local_timestamp, 
                       sender_username, thread_title, message_text, reaction_emoji, reel_url 
                FROM reaction_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return []

def clear_logs():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reaction_logs")
            conn.commit()
    except Exception:
        pass

# Initialize database on import
init_db()
