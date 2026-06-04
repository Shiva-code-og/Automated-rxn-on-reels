import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_v2.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create settings table (user-specific)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY (user_id, key)
            )
        """)
        
        # Create processed messages table (user-specific)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                user_id TEXT,
                message_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, message_id)
            )
        """)
        
        # Create reaction logs table (user-specific)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sender_username TEXT,
                thread_title TEXT,
                message_text TEXT,
                reaction_emoji TEXT,
                reel_url TEXT
            )
        """)
        
        # Create instagram sessions table for saving instagrapi session dicts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS instagram_sessions (
                user_id TEXT PRIMARY KEY,
                session_data TEXT
            )
        """)
        conn.commit()

def get_setting(user_id: str, key: str, default: str = None) -> str:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default
    except Exception:
        return default

def save_setting(user_id: str, key: str, value: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)", (user_id, key, str(value)))
        conn.commit()

def get_all_settings(user_id: str):
    settings = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings WHERE user_id = ?", (user_id,))
            rows = cursor.fetchall()
            for row in rows:
                settings[row["key"]] = row["value"]
    except Exception:
        pass
    return settings

def is_message_processed(user_id: str, message_id: str) -> bool:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_messages WHERE user_id = ? AND message_id = ?", (user_id, message_id))
            return cursor.fetchone() is not None
    except Exception:
        return False

def mark_message_processed(user_id: str, message_id: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO processed_messages (user_id, message_id) VALUES (?, ?)", (user_id, message_id))
            conn.commit()
    except Exception:
        pass

def add_log(user_id: str, sender_username: str, thread_title: str, message_text: str, reaction_emoji: str, reel_url: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reaction_logs (user_id, sender_username, thread_title, message_text, reaction_emoji, reel_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, sender_username, thread_title, message_text, reaction_emoji, reel_url))
            conn.commit()
    except Exception as e:
        print(f"Error adding log: {e}")

def get_logs(user_id: str, limit: int = 100):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, datetime(timestamp, 'localtime') as local_timestamp, 
                       sender_username, thread_title, message_text, reaction_emoji, reel_url 
                FROM reaction_logs 
                WHERE user_id = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return []

def clear_logs(user_id: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reaction_logs WHERE user_id = ?", (user_id,))
            conn.commit()
    except Exception:
        pass

def get_instagram_session(user_id: str) -> str:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT session_data FROM instagram_sessions WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return row["session_data"]
            return None
    except Exception:
        return None

def save_instagram_session(user_id: str, session_data: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO instagram_sessions (user_id, session_data) VALUES (?, ?)", (user_id, session_data))
        conn.commit()

def delete_instagram_session(user_id: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM instagram_sessions WHERE user_id = ?", (user_id,))
        conn.commit()

# Initialize database on import
init_db()
