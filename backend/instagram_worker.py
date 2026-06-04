import threading
import time
import re
import random
import os
import sys
import json
from datetime import datetime, timezone
from instagrapi import Client
from instagrapi.exceptions import TwoFactorRequired, LoginRequired, ChallengeRequired
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(ENV_PATH)

from . import database
from .emoji_analyzer import get_smart_emoji, analyze_with_gemini

# Fix Windows console encoding - prevents crashes on emoji/unicode characters
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def safe_print(*args, **kwargs):
    """Print that won't crash on Windows due to Unicode encoding errors."""
    kwargs['flush'] = True
    try:
        print(*args, **kwargs)
    except (UnicodeEncodeError, UnicodeDecodeError):
        text = ' '.join(str(a) for a in args)
        print(text.encode('ascii', errors='replace').decode('ascii'), **kwargs)

class InstagramWorker:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.cl = Client()
        self.status = "idle"  # idle, logging_in, 2fa_needed, connected, error
        self.error_message = ""
        self.temp_password = ""
        
        self.polling_thread = None
        self.stop_event = threading.Event()
        self.last_check_time = 0
        self.start_time = datetime.now(timezone.utc)
        
        # Cache to map user ID to username to reduce API calls
        self.username_cache = {}
        
        # In-memory set for fast dedup
        self.processed_ids = set()
        
        # Load session from database if exists on startup
        self.try_load_session()

    def try_load_session(self):
        session_data = database.get_instagram_session(self.user_id)
        session_restored = False
        
        if session_data:
            safe_print(f"[{self.user_id}] Session found in DB, attempting to restore...")
            try:
                settings_dict = json.loads(session_data)
                self.cl.set_settings(settings_dict)
                
                # Check settings to see if username is saved
                saved_username = database.get_setting(self.user_id, "instagram_username")
                if saved_username:
                    self.cl.get_timeline_feed()
                    self.status = "connected"
                    safe_print(f"[{self.user_id}] Successfully restored session.")
                    session_restored = True
                else:
                    self.status = "idle"
            except Exception as e:
                safe_print(f"[{self.user_id}] Could not load cached session: {e}")
                self.status = "idle"
                self.cl = Client()
                
        # If session file not found or invalid, check if we have saved credentials to login
        if not session_restored:
            saved_username = database.get_setting(self.user_id, "instagram_username")
            saved_password = database.get_setting(self.user_id, "instagram_password")
            if saved_username and saved_password:
                safe_print(f"[{self.user_id}] Attempting automatic login using saved credentials...")
                res = self.login(saved_username, saved_password, force_fresh=True)
                if res["status"] == "success":
                    safe_print(f"[{self.user_id}] Automatic login successful!")
                else:
                    safe_print(f"[{self.user_id}] Automatic login failed: {res['message']}")

    def save_session_to_db(self):
        try:
            settings_dict = self.cl.get_settings()
            session_data = json.dumps(settings_dict)
            database.save_instagram_session(self.user_id, session_data)
        except Exception as e:
            safe_print(f"[{self.user_id}] Error saving session to DB: {e}")

    def login(self, username, password, force_fresh=False):
        self.status = "logging_in"
        self.error_message = ""
        self.temp_password = password
        
        self.cl = Client()
        
        session_data = database.get_instagram_session(self.user_id)
        if not force_fresh and session_data:
            try:
                settings_dict = json.loads(session_data)
                self.cl.set_settings(settings_dict)
                self.cl.get_timeline_feed()
                self.status = "connected"
                self.temp_password = ""
                return {"status": "success", "message": "Logged in successfully via restored session!"}
            except Exception:
                self.cl = Client()
                database.delete_instagram_session(self.user_id)
                
        try:
            safe_print(f"[{self.user_id}] Attempting to log in...")
            self.cl.login(username, password)
            self.save_session_to_db()
            self.status = "connected"
            self.temp_password = ""
            
            database.save_setting(self.user_id, "instagram_username", username)
            database.save_setting(self.user_id, "instagram_password", password)
            
            if database.get_setting(self.user_id, "is_running", "false") == "true":
                self.start_monitoring()
                
            return {"status": "success", "message": "Logged in successfully!"}
            
        except TwoFactorRequired as e:
            safe_print(f"[{self.user_id}] 2FA code required for login.")
            self.status = "2fa_needed"
            return {"status": "2fa_needed", "message": "Two-factor authentication code required."}
            
        except ChallengeRequired as e:
            safe_print(f"[{self.user_id}] Challenge checkpoint required by Instagram.")
            self.status = "error"
            self.error_message = "Instagram requires a security check. Please log in from your phone app first, resolve the challenge, and try again."
            return {"status": "error", "message": self.error_message}
            
        except Exception as e:
            safe_print(f"[{self.user_id}] Login failed: {e}")
            self.status = "error"
            self.error_message = str(e)
            return {"status": "error", "message": str(e)}

    def login_2fa(self, code):
        if self.status != "2fa_needed":
            return {"status": "error", "message": "No 2FA flow is active."}
            
        try:
            safe_print(f"[{self.user_id}] Attempting 2FA login with code {code}...")
            self.cl.two_factor_login(code)
            self.save_session_to_db()
            self.status = "connected"
            
            database.save_setting(self.user_id, "instagram_username", self.user_id)
            database.save_setting(self.user_id, "instagram_password", self.temp_password)
            self.temp_password = ""
            
            if database.get_setting(self.user_id, "is_running", "false") == "true":
                self.start_monitoring()
                
            return {"status": "success", "message": "Logged in successfully with 2FA!"}
        except Exception as e:
            safe_print(f"[{self.user_id}] 2FA login failed: {e}")
            self.status = "error"
            self.error_message = str(e)
            return {"status": "error", "message": str(e)}

    def logout(self):
        safe_print(f"[{self.user_id}] Logging out and clearing session...")
        self.cl = Client()
        database.delete_instagram_session(self.user_id)
        self.status = "idle"
        database.save_setting(self.user_id, "instagram_username", "")
        database.save_setting(self.user_id, "instagram_password", "")
        return {"status": "success", "message": "Logged out successfully."}

    def start_monitoring(self):
        if self.status != "connected":
            return {"status": "error", "message": "Please connect your Instagram account first."}
            
        if self.polling_thread and self.polling_thread.is_alive():
            return {"status": "success", "message": "Worker is already running."}
            
        self.stop_event.clear()
        
        from datetime import timedelta
        self.start_time = datetime.now(timezone.utc) - timedelta(hours=12)
        
        self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.polling_thread.start()
        database.save_setting(self.user_id, "is_running", "true")
        safe_print(f"[{self.user_id}] DM monitoring background worker started.")
        return {"status": "success", "message": "Monitoring worker started."}

    def stop_monitoring(self):
        database.save_setting(self.user_id, "is_running", "false")
        if not self.polling_thread or not self.polling_thread.is_alive():
            return {"status": "success", "message": "Worker is already stopped."}
            
        self.stop_event.set()
        self.polling_thread.join(timeout=3)
        safe_print(f"[{self.user_id}] DM monitoring background worker stopped.")
        return {"status": "success", "message": "Monitoring worker stopped."}

    def is_worker_running(self):
        return self.polling_thread is not None and self.polling_thread.is_alive()

    def _polling_loop(self):
        self._check_and_react()
        self.last_check_time = time.time()
        
        while not self.stop_event.is_set():
            interval_str = database.get_setting(self.user_id, "poll_interval", "5")
            try:
                poll_interval = int(interval_str) * 60
            except ValueError:
                poll_interval = 300
                
            if time.time() - self.last_check_time >= poll_interval:
                self._check_and_react()
                self.last_check_time = time.time()
                
            time.sleep(1)

    def _check_and_react(self):
        is_running_setting = database.get_setting(self.user_id, "is_running", "false") == "true"
        if not is_running_setting:
            safe_print(f"[{self.user_id}] Worker check aborted: system is off.")
            return

        if self.status != "connected":
            safe_print(f"[{self.user_id}] Worker paused check: client not connected.")
            return
            
        safe_print(f"[{self.user_id}] Background worker starting DM check...")
        try:
            try:
                self.cl.get_timeline_feed()
            except LoginRequired:
                safe_print(f"[{self.user_id}] Session expired during check, attempting auto-reconnect...")
                saved_user = database.get_setting(self.user_id, "instagram_username")
                saved_pass = database.get_setting(self.user_id, "instagram_password")
                if saved_user and saved_pass:
                    self.login(saved_user, saved_pass, force_fresh=True)
                    if self.status != "connected":
                        safe_print(f"[{self.user_id}] Auto-reconnect failed.")
                        return
                else:
                    self.status = "error"
                    self.error_message = "Session expired. Please log in again."
                    return
            except ChallengeRequired:
                self.status = "error"
                self.error_message = "Instagram requires a security check (challenge). Please log in via your phone app first."
                return
            except Exception as e:
                safe_print(f"[{self.user_id}] Session validation check failed: {e}")
                return
            
            react_target = database.get_setting(self.user_id, "react_target", "all")
            specific_str = database.get_setting(self.user_id, "specific_usernames", "")
            selected_emojis_str = database.get_setting(self.user_id, "selected_emojis", "❤️,🔥,😂,😮,👏")
            use_random_emoji = database.get_setting(self.user_id, "use_random_emoji", "false") == "true"
            
            target_usernames = {u.strip().lstrip("@").lower() for u in specific_str.split(",") if u.strip()}
            emoji_list = [e.strip() for e in selected_emojis_str.split(",") if e.strip()]
            if not emoji_list:
                emoji_list = ["❤️", "🔥", "😂", "😮", "👏"]
                
            threads = self.cl.direct_threads(amount=10)
            
            for thread in threads:
                if self.stop_event.is_set():
                    break
                    
                for u in thread.users:
                    self.username_cache[str(u.pk)] = u.username
                    
                messages = self.cl.direct_messages(thread_id=thread.id, amount=15)
                
                for msg in messages:
                    if self.stop_event.is_set():
                        break
                        
                    if str(msg.user_id) == str(self.cl.user_id):
                        continue
                        
                    msg_time = msg.timestamp
                    if msg_time.tzinfo is not None:
                        msg_time_utc = msg_time.astimezone(timezone.utc)
                    else:
                        msg_time_utc = msg_time.replace(tzinfo=timezone.utc)
                        
                    if msg_time_utc < self.start_time:
                        continue
                        
                    sender_username = self.username_cache.get(str(msg.user_id))
                    if not sender_username:
                        try:
                            user_info = self.cl.user_info(msg.user_id)
                            sender_username = user_info.username
                            self.username_cache[str(msg.user_id)] = sender_username
                        except Exception:
                            sender_username = "unknown_user"
                            
                    if react_target == "specific" and sender_username.lower() not in target_usernames:
                        continue
                        
                    message_id_str = str(msg.id)
                    if message_id_str in self.processed_ids or database.is_message_processed(self.user_id, message_id_str):
                        self.processed_ids.add(message_id_str)
                        continue
                        
                    is_reel = False
                    reel_url = ""
                    code = ""
                    media_pk = None
                    
                    if msg.item_type in ["clip", "xma_clip", "media_share", "xma_media_share"]:
                        is_reel = True
                        if hasattr(msg, "clip") and msg.clip:
                            if hasattr(msg.clip, "code"):
                                code = msg.clip.code
                            if hasattr(msg.clip, "pk"):
                                media_pk = msg.clip.pk
                        elif hasattr(msg, "media_share") and msg.media_share:
                            media = msg.media_share
                            product_type = getattr(media, "product_type", "")
                            if product_type == "clips":
                                if hasattr(media, "code"):
                                    code = media.code
                                if hasattr(media, "pk"):
                                    media_pk = media.pk
                            else:
                                is_reel = False
                        elif hasattr(msg, "xma_share") and msg.xma_share:
                            xma = msg.xma_share
                            video_url_val = None
                            if isinstance(xma, dict):
                                video_url_val = xma.get("video_url")
                            elif hasattr(xma, "video_url"):
                                video_url_val = getattr(xma, "video_url")
                                
                            if video_url_val:
                                url_str = str(video_url_val)
                                code_match = re.search(r"/reel/([a-zA-Z0-9_-]+)", url_str)
                                if code_match:
                                    reel_url = url_str
                                    code = code_match.group(1)
                                    pk_match = re.search(r"id=(\d+)", url_str)
                                    if pk_match:
                                        media_pk = pk_match.group(1)
                                else:
                                    is_reel = False
                                    
                        if is_reel:
                            if code and not reel_url:
                                reel_url = f"https://www.instagram.com/reel/{code}/"
                            elif not reel_url:
                                reel_url = f"https://www.instagram.com/direct/t/{thread.id}"
                            
                    elif msg.text:
                        match = re.search(r"https?://(?:www\.)?instagram\.com/reel/([a-zA-Z0-9_-]+)", msg.text)
                        if match:
                            is_reel = True
                            reel_url = match.group(0)
                            code = match.group(1)
                            
                    if is_reel:
                        self.processed_ids.add(message_id_str)
                        database.mark_message_processed(self.user_id, message_id_str)
                        
                        reel_caption = ""
                        try:
                            if hasattr(msg, "clip") and msg.clip and hasattr(msg.clip, "caption_text") and msg.clip.caption_text:
                                reel_caption = msg.clip.caption_text
                            elif hasattr(msg, "media_share") and msg.media_share and hasattr(msg.media_share, "caption_text") and msg.media_share.caption_text:
                                reel_caption = msg.media_share.caption_text
                                        
                            if not media_pk and code:
                                try:
                                    media_pk = self.cl.media_pk_from_code(code)
                                except Exception:
                                    pass
                                    
                            if not reel_caption and media_pk:
                                try:
                                    media_info = self.cl.media_info_v1(str(media_pk))
                                    if media_info and media_info.caption_text:
                                        reel_caption = media_info.caption_text
                                except Exception:
                                    pass
                            
                            if not reel_caption and code:
                                try:
                                    media_pk_from_code = self.cl.media_pk_from_code(code)
                                    if media_pk_from_code:
                                        media_info = self.cl.media_info_v1(str(media_pk_from_code))
                                        if media_info and media_info.caption_text:
                                            reel_caption = media_info.caption_text
                                except Exception:
                                    pass
                        except Exception:
                            pass
                            
                        comments_list = []
                        if media_pk:
                            try:
                                comments = self.cl.media_comments(str(media_pk), amount=30)
                                comments_list = [c.text for c in comments]
                            except Exception:
                                pass
                        
                        use_gemini = database.get_setting(self.user_id, "use_gemini", "false") == "true"
                        gemini_api_key = os.getenv("GEMINI_API_KEY", database.get_setting(self.user_id, "gemini_api_key", ""))
                        
                        emoji = None
                        if use_gemini and gemini_api_key:
                            try:
                                emoji = analyze_with_gemini(
                                    api_key=gemini_api_key,
                                    caption=reel_caption,
                                    comments=comments_list,
                                    message_text=msg.text
                                )
                            except Exception:
                                pass
                        
                        if not emoji:
                            emoji = get_smart_emoji(
                                caption_text=reel_caption,
                                comments=comments_list,
                                message_text=msg.text,
                                fallback_emojis=emoji_list,
                                use_random_fallback=use_random_emoji
                            )
                        
                        caption_preview = (reel_caption[:80] + '...') if len(reel_caption) > 80 else reel_caption
                        safe_print(f"[{self.user_id}] Reacting to reel from {sender_username} | Emoji: {emoji}")
                        
                        try:
                            self.cl.direct_send_reaction(
                                thread_id=thread.id,
                                message_id=msg.id,
                                emoji=emoji
                            )
                            
                            text_summary = reel_caption[:100] if reel_caption else (msg.text or "Shared Reel")
                            database.add_log(
                                user_id=self.user_id,
                                sender_username=sender_username,
                                thread_title=thread.thread_title or "Direct Message",
                                message_text=text_summary,
                                reaction_emoji=emoji,
                                reel_url=reel_url
                            )
                            
                            time.sleep(random.uniform(2.0, 5.0))
                            
                        except Exception as react_err:
                            safe_print(f"[{self.user_id}] Failed to react to message {message_id_str}: {react_err}")
                            
        except Exception as e:
            safe_print(f"[{self.user_id}] Error during DM check: {e}")

class WorkerManager:
    def __init__(self):
        self.workers = {}
        self.lock = threading.Lock()

    def get_worker(self, user_id: str) -> InstagramWorker:
        with self.lock:
            if user_id not in self.workers:
                self.workers[user_id] = InstagramWorker(user_id)
            return self.workers[user_id]

    def remove_worker(self, user_id: str):
        with self.lock:
            if user_id in self.workers:
                worker = self.workers[user_id]
                worker.stop_monitoring()
                del self.workers[user_id]

# Global worker manager
worker_manager = WorkerManager()
