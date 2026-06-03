import threading
import time
import re
import random
import os
import sys
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
        # Fallback: encode to ascii with replacement chars
        text = ' '.join(str(a) for a in args)
        print(text.encode('ascii', errors='replace').decode('ascii'), **kwargs)

SESSION_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "session.json")

class InstagramWorker:
    def __init__(self):
        self.cl = Client()
        self.status = "idle"  # idle, logging_in, 2fa_needed, connected, error
        self.error_message = ""
        self.username = ""
        self.temp_username = ""
        self.temp_password = ""
        
        self.polling_thread = None
        self.stop_event = threading.Event()
        self.last_check_time = 0
        self.start_time = datetime.now(timezone.utc)
        
        # Cache to map user ID to username to reduce API calls
        self.username_cache = {}
        
        # In-memory set for fast dedup (prevents re-processing even if DB write is slow)
        self.processed_ids = set()
        
        # Load session from file if exists on startup
        self.try_load_session()

    def try_load_session(self):
        session_restored = False
        if os.path.exists(SESSION_PATH):
            safe_print("Session file found, attempting to restore session...")
            try:
                self.cl.load_settings(SESSION_PATH)
                # Check settings to see if username is saved
                saved_username = database.get_setting("instagram_username")
                if saved_username:
                    self.username = saved_username
                    # Verify login status
                    self.cl.get_timeline_feed()
                    self.status = "connected"
                    safe_print(f"Successfully restored session for {self.username}")
                    session_restored = True
                else:
                    self.status = "idle"
            except Exception as e:
                safe_print(f"Could not load cached session: {e}")
                self.status = "idle"
                # If loading settings failed, reset client
                self.cl = Client()
                
        # If session file not found or invalid, check if we have saved credentials to login
        if not session_restored:
            saved_username = database.get_setting("instagram_username")
            saved_password = database.get_setting("instagram_password")
            if saved_username and saved_password:
                safe_print(f"Attempting automatic login using saved credentials for {saved_username}...")
                res = self.login(saved_username, saved_password, force_fresh=True)
                if res["status"] == "success":
                    safe_print("Automatic login successful!")
                else:
                    safe_print(f"Automatic login failed: {res['message']}")

    def login(self, username, password, force_fresh=False):
        self.status = "logging_in"
        self.error_message = ""
        self.temp_username = username
        self.temp_password = password
        
        # Reset client for a clean login attempt
        self.cl = Client()
        
        # Try loading settings if they exist (just in case)
        if not force_fresh and os.path.exists(SESSION_PATH):
            try:
                self.cl.load_settings(SESSION_PATH)
                # Verify that the session is actually valid
                self.cl.get_timeline_feed()
                self.status = "connected"
                self.username = username
                self.temp_username = ""
                self.temp_password = ""
                return {"status": "success", "message": "Logged in successfully via restored session!"}
            except Exception:
                # Restored session is invalid, clear settings and do fresh login
                self.cl = Client()
                if os.path.exists(SESSION_PATH):
                    try:
                        os.remove(SESSION_PATH)
                    except Exception:
                        pass
                
        try:
            safe_print(f"Attempting to log in as {username}...")
            self.cl.login(username, password)
            self.cl.dump_settings(SESSION_PATH)
            self.status = "connected"
            self.username = username
            self.temp_username = ""
            self.temp_password = ""
            
            # Save settings in DB
            database.save_setting("instagram_username", username)
            database.save_setting("instagram_password", password) # saved locally for reconnects
            
            # Auto-start monitoring if it was marked as running in settings
            if database.get_setting("is_running", "false") == "true":
                self.start_monitoring()
                
            return {"status": "success", "message": "Logged in successfully!"}
            
        except TwoFactorRequired as e:
            safe_print("2FA code required for login.")
            self.status = "2fa_needed"
            return {"status": "2fa_needed", "message": "Two-factor authentication code required."}
            
        except ChallengeRequired as e:
            safe_print("Challenge checkpoint required by Instagram.")
            self.status = "error"
            self.error_message = "Instagram requires a security check. Please log in from your phone app first, resolve the challenge, and try again."
            return {"status": "error", "message": self.error_message}
            
        except Exception as e:
            safe_print(f"Login failed: {e}")
            self.status = "error"
            self.error_message = str(e)
            return {"status": "error", "message": str(e)}

    def login_2fa(self, code):
        if self.status != "2fa_needed":
            return {"status": "error", "message": "No 2FA flow is active."}
            
        try:
            safe_print(f"Attempting 2FA login with code {code}...")
            # Complete 2FA login
            self.cl.two_factor_login(code)
            self.cl.dump_settings(SESSION_PATH)
            self.status = "connected"
            self.username = self.temp_username
            
            # Save settings in DB
            database.save_setting("instagram_username", self.username)
            database.save_setting("instagram_password", self.temp_password)
            
            self.temp_username = ""
            self.temp_password = ""
            
            # Auto-start monitoring if it was marked as running in settings
            if database.get_setting("is_running", "false") == "true":
                self.start_monitoring()
                
            return {"status": "success", "message": "Logged in successfully with 2FA!"}
        except Exception as e:
            safe_print(f"2FA login failed: {e}")
            self.status = "error"
            self.error_message = str(e)
            return {"status": "error", "message": str(e)}

    def logout(self):
        safe_print("Logging out and clearing session...")
        self.cl = Client()
        if os.path.exists(SESSION_PATH):
            try:
                os.remove(SESSION_PATH)
            except Exception:
                pass
        self.status = "idle"
        self.username = ""
        database.save_setting("instagram_username", "")
        database.save_setting("instagram_password", "")
        return {"status": "success", "message": "Logged out successfully."}

    def start_monitoring(self):
        if self.status != "connected":
            return {"status": "error", "message": "Please connect your Instagram account first."}
            
        if self.polling_thread and self.polling_thread.is_alive():
            return {"status": "success", "message": "Worker is already running."}
            
        self.stop_event.clear()
        
        # Set start_time to 12 hours ago to catch up on recently sent reels during downtime
        from datetime import timedelta
        self.start_time = datetime.now(timezone.utc) - timedelta(hours=12)
        
        self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.polling_thread.start()
        database.save_setting("is_running", "true")
        safe_print("DM monitoring background worker started.")
        return {"status": "success", "message": "Monitoring worker started."}

    def stop_monitoring(self):
        database.save_setting("is_running", "false")
        if not self.polling_thread or not self.polling_thread.is_alive():
            return {"status": "success", "message": "Worker is already stopped."}
            
        self.stop_event.set()
        self.polling_thread.join(timeout=3)
        safe_print("DM monitoring background worker stopped.")
        return {"status": "success", "message": "Monitoring worker stopped."}

    def is_worker_running(self):
        return self.polling_thread is not None and self.polling_thread.is_alive()

    def _polling_loop(self):
        # Initial check
        self._check_and_react()
        self.last_check_time = time.time()
        
        while not self.stop_event.is_set():
            # Retrieve poll interval from settings (default to 5 minutes)
            interval_str = database.get_setting("poll_interval", "5")
            try:
                poll_interval = int(interval_str) * 60
            except ValueError:
                poll_interval = 300
                
            # Wakes up every second to check for shutdown, but runs check only when interval elapses
            if time.time() - self.last_check_time >= poll_interval:
                self._check_and_react()
                self.last_check_time = time.time()
                
            time.sleep(1)

    def _check_and_react(self):
        # Verify if the system is on (monitoring is active)
        is_running_setting = database.get_setting("is_running", "false") == "true"
        if not is_running_setting:
            safe_print("Worker check aborted: system is off.")
            return

        if self.status != "connected":
            safe_print("Worker paused check: client not connected.")
            return
            
        safe_print("Background worker starting DM check...")
        try:
            # Refresh session to prevent expiration
            try:
                self.cl.get_timeline_feed()
            except LoginRequired:
                safe_print("Session expired during check, attempting automatic reconnect...")
                saved_user = database.get_setting("instagram_username")
                saved_pass = database.get_setting("instagram_password")
                if saved_user and saved_pass:
                    # Force a fresh login to bypass the expired session settings
                    self.login(saved_user, saved_pass, force_fresh=True)
                    if self.status != "connected":
                        safe_print("Auto-reconnect failed.")
                        return
                else:
                    self.status = "error"
                    self.error_message = "Session expired. Please log in again."
                    safe_print("No saved credentials for auto-reconnect.")
                    return
            except ChallengeRequired:
                self.status = "error"
                self.error_message = "Instagram requires a security check (challenge). Please log in via your phone app first."
                safe_print("Instagram challenge required during check.")
                return
            except Exception as e:
                safe_print(f"Session validation check failed (possible network issue): {e}")
                return
            
            # Fetch target config
            react_target = database.get_setting("react_target", "all")
            specific_str = database.get_setting("specific_usernames", "")
            selected_emojis_str = database.get_setting("selected_emojis", "❤️,🔥,😂,😮,👏")
            use_random_emoji = database.get_setting("use_random_emoji", "false") == "true"
            
            target_usernames = {u.strip().lstrip("@").lower() for u in specific_str.split(",") if u.strip()}
            emoji_list = [e.strip() for e in selected_emojis_str.split(",") if e.strip()]
            if not emoji_list:
                emoji_list = ["❤️", "🔥", "😂", "😮", "👏"]
                
            # Get latest direct threads
            threads = self.cl.direct_threads(amount=10)
            
            for thread in threads:
                if self.stop_event.is_set():
                    break
                    
                # Cache thread users for username lookup
                for u in thread.users:
                    self.username_cache[str(u.pk)] = u.username
                    
                messages = self.cl.direct_messages(thread_id=thread.id, amount=15)
                
                for msg in messages:
                    if self.stop_event.is_set():
                        break
                        
                    # Skip if sent by me
                    if str(msg.user_id) == str(self.cl.user_id):
                        continue
                        
                    # Filter messages sent before the worker became active
                    msg_time = msg.timestamp
                    if msg_time.tzinfo is not None:
                        msg_time_utc = msg_time.astimezone(timezone.utc)
                    else:
                        msg_time_utc = msg_time.replace(tzinfo=timezone.utc)
                        
                    if msg_time_utc < self.start_time:
                        continue
                        
                    # Find sender's username
                    sender_username = self.username_cache.get(str(msg.user_id))
                    if not sender_username:
                        # Fallback: resolve user info (rate limit hazard, so cache immediately)
                        try:
                            user_info = self.cl.user_info(msg.user_id)
                            sender_username = user_info.username
                            self.username_cache[str(msg.user_id)] = sender_username
                        except Exception:
                            sender_username = "unknown_user"
                            
                    # Filter by target friends
                    if react_target == "specific" and sender_username.lower() not in target_usernames:
                        continue
                        
                    # Skip if already processed (check both in-memory set AND database)
                    message_id_str = str(msg.id)
                    if message_id_str in self.processed_ids or database.is_message_processed(message_id_str):
                        self.processed_ids.add(message_id_str)  # sync to memory
                        continue
                        
                    # Check if the message contains a Reel
                    is_reel = False
                    reel_url = ""
                    code = ""
                    media_pk = None
                    
                    # 1. Check item_type
                    if msg.item_type in ["clip", "xma_clip", "media_share", "xma_media_share"]:
                        is_reel = True
                        
                        # Clip structures are always Reels
                        if hasattr(msg, "clip") and msg.clip:
                            if hasattr(msg.clip, "code"):
                                code = msg.clip.code
                            if hasattr(msg.clip, "pk"):
                                media_pk = msg.clip.pk
                        # For media_share, make sure it is actually a Reel (clips product type)
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
                                
                        # Handle modern xma_share structures (which represents modern Reels shared in DMs)
                        elif hasattr(msg, "xma_share") and msg.xma_share:
                            xma = msg.xma_share
                            video_url_val = None
                            if isinstance(xma, dict):
                                video_url_val = xma.get("video_url")
                            elif hasattr(xma, "video_url"):
                                video_url_val = getattr(xma, "video_url")
                                
                            if video_url_val:
                                url_str = str(video_url_val)
                                # Only match /reel/ to ensure it is a Reel
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
                            
                    # 2. Check regex matching in text links (only match /reel/)
                    elif msg.text:
                        match = re.search(r"https?://(?:www\.)?instagram\.com/reel/([a-zA-Z0-9_-]+)", msg.text)
                        if match:
                            is_reel = True
                            reel_url = match.group(0)
                            code = match.group(1)
                            
                    if is_reel:
                        # Mark as processed IMMEDIATELY to prevent duplicates
                        # (even if the reaction API call fails, we don't want to spam)
                        self.processed_ids.add(message_id_str)
                        database.mark_message_processed(message_id_str)
                        
                        # --- Smart Emoji: Fetch reel caption and comments, then analyze content ---
                        reel_caption = ""
                        try:
                            # Debug logging
                            safe_print(f"DEBUG: Extracting caption/media info for item_type={msg.item_type}")
                            
                            # Get caption from clip if present
                            if hasattr(msg, "clip") and msg.clip and hasattr(msg.clip, "caption_text") and msg.clip.caption_text:
                                reel_caption = msg.clip.caption_text
                            # Get caption from media_share if present
                            elif hasattr(msg, "media_share") and msg.media_share and hasattr(msg.media_share, "caption_text") and msg.media_share.caption_text:
                                reel_caption = msg.media_share.caption_text
                                        
                            # Resolve media_pk from code if needed
                            if not media_pk and code:
                                try:
                                    media_pk = self.cl.media_pk_from_code(code)
                                except Exception as pk_err:
                                    safe_print(f"  Could not get media pk from code: {pk_err}")
                                    
                            # If we couldn't get caption from message, try fetching media info
                            if not reel_caption and media_pk:
                                try:
                                    media_info = self.cl.media_info_v1(str(media_pk))
                                    if media_info and media_info.caption_text:
                                        reel_caption = media_info.caption_text
                                except Exception as mi_err:
                                    safe_print(f"  Could not fetch media info: {mi_err}")
                            
                            # Also try fetching via media code if we have it
                            if not reel_caption and code:
                                try:
                                    media_pk_from_code = self.cl.media_pk_from_code(code)
                                    if media_pk_from_code:
                                        media_info = self.cl.media_info_v1(str(media_pk_from_code))
                                        if media_info and media_info.caption_text:
                                            reel_caption = media_info.caption_text
                                except Exception as mc_err:
                                    safe_print(f"  Could not fetch media by code: {mc_err}")
                                    
                        except Exception as caption_err:
                            safe_print(f"  Could not extract caption: {caption_err}")
                            
                        # Fetch comments from Reel if media_pk is available
                        comments_list = []
                        if media_pk:
                            try:
                                safe_print(f"  Fetching comments for media {media_pk}...")
                                comments = self.cl.media_comments(str(media_pk), amount=30)
                                comments_list = [c.text for c in comments]
                                safe_print(f"  Successfully fetched {len(comments_list)} comments.")
                            except Exception as comment_err:
                                safe_print(f"  Could not fetch comments: {comment_err}")
                        
                        # Check if Gemini AI Analysis is enabled
                        use_gemini = database.get_setting("use_gemini", "false") == "true"
                        gemini_api_key = os.getenv("GEMINI_API_KEY", database.get_setting("gemini_api_key", ""))
                        
                        emoji = None
                        if use_gemini and gemini_api_key:
                            try:
                                safe_print("  Analyzing content using Gemini AI...")
                                emoji = analyze_with_gemini(
                                    api_key=gemini_api_key,
                                    caption=reel_caption,
                                    comments=comments_list,
                                    message_text=msg.text
                                )
                                if emoji:
                                    safe_print(f"  Gemini chose reaction: {emoji}")
                                else:
                                    safe_print("  Gemini returned empty response, falling back to smart analyzer.")
                            except Exception as gemini_err:
                                safe_print(f"  Gemini analysis failed: {gemini_err}. Falling back to smart analyzer.")
                        
                        # Pick emoji based on reel content & comments analysis (fallback if Gemini disabled/failed)
                        if not emoji:
                            emoji = get_smart_emoji(
                                caption_text=reel_caption,
                                comments=comments_list,
                                message_text=msg.text, # Pass companion text
                                fallback_emojis=emoji_list,
                                use_random_fallback=use_random_emoji
                            )
                        
                        caption_preview = (reel_caption[:80] + '...') if len(reel_caption) > 80 else reel_caption
                        safe_print(f"Reacting to reel from {sender_username} | Caption: '{caption_preview}' | Emoji: {emoji}")
                        
                        try:
                            # Send direct reaction to the specific message
                            self.cl.direct_send_reaction(
                                thread_id=thread.id,
                                message_id=msg.id,
                                emoji=emoji
                            )
                            
                            # Add to reaction logs
                            text_summary = reel_caption[:100] if reel_caption else (msg.text or "Shared Reel media attachment")
                            database.add_log(
                                sender_username=sender_username,
                                thread_title=thread.thread_title or "Direct Message",
                                message_text=text_summary,
                                reaction_emoji=emoji,
                                reel_url=reel_url
                            )
                            
                            safe_print(f"  -> Reaction sent successfully!")
                            
                            # Anti-ban sleep delay: 2 to 5 seconds
                            time.sleep(random.uniform(2.0, 5.0))
                            
                        except Exception as react_err:
                            safe_print(f"Failed to react to message {message_id_str}: {react_err}")
                            
        except Exception as e:
            safe_print(f"Error during DM check: {e}")

# Global worker instance
instagram_worker = InstagramWorker()
