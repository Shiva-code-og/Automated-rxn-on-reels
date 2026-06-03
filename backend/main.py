from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(ENV_PATH)

from .database import get_setting, save_setting, get_all_settings, get_logs, clear_logs
from .instagram_worker import instagram_worker

app = FastAPI(title="Automated Reels Reaction API")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"An internal server error occurred: {str(exc)}"}
    )

# Define request schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class TwoFactorRequest(BaseModel):
    code: str

class ConfigUpdateRequest(BaseModel):
    react_target: str
    specific_usernames: str
    selected_emojis: str
    use_random_emoji: bool
    poll_interval: int
    use_gemini: bool
    gemini_api_key: str

# Define absolute paths for frontend mounting
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

@app.on_event("startup")
def startup_event():
    try:
        # If worker was marked running and session is restored, restart background monitoring
        is_running_setting = get_setting("is_running", "false") == "true"
        if is_running_setting and instagram_worker.status == "connected":
            print("Restoring background worker monitoring on startup...")
            instagram_worker.start_monitoring()
    except Exception as e:
        print(f"Error during startup: {e}")

@app.get("/api/status")
def get_status():
    logs = get_logs(limit=1)
    logs_count = len(get_logs(limit=10000)) # Count total logs
    
    return {
        "status": instagram_worker.status,
        "username": instagram_worker.username,
        "error_message": instagram_worker.error_message,
        "is_running": instagram_worker.is_worker_running(),
        "logs_count": logs_count
    }

@app.post("/api/login")
def login(data: LoginRequest, background_tasks: BackgroundTasks):
    print(f"API Login: Attempting connection for user '{data.username}'...")
    res = instagram_worker.login(data.username, data.password)
    if res["status"] == "error":
        print(f"API Login: Connection failed for user '{data.username}': {res['message']}")
        raise HTTPException(status_code=400, detail=res["message"])
    print(f"API Login: Connection result -> {res['status']}")
    return res

@app.post("/api/login/2fa")
def login_2fa(data: TwoFactorRequest):
    print(f"API Login 2FA: Submitting code '{data.code}'...")
    res = instagram_worker.login_2fa(data.code)
    if res["status"] == "error":
        print(f"API Login 2FA: Code verification failed: {res['message']}")
        raise HTTPException(status_code=400, detail=res["message"])
    print("API Login 2FA: Verified and connected successfully!")
    return res

@app.post("/api/logout")
def logout():
    print("API Logout: Disconnecting Instagram account...")
    instagram_worker.stop_monitoring()
    res = instagram_worker.logout()
    print("API Logout: Account disconnected.")
    return res

def update_env_file(key: str, value: str):
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            pass
            
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
            
    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{key}={value}\n")
        
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Error writing to .env file: {e}")

@app.get("/api/config")
def get_config():
    # Retrieve configurations, use default values if not defined
    api_key = os.getenv("GEMINI_API_KEY", get_setting("gemini_api_key", ""))
    masked_key = "••••••••" if api_key else ""
    return {
        "react_target": get_setting("react_target", "all"),
        "specific_usernames": get_setting("specific_usernames", ""),
        "selected_emojis": get_setting("selected_emojis", "❤️,🔥,😂,😮,👏"),
        "use_random_emoji": get_setting("use_random_emoji", "false") == "true",
        "poll_interval": int(get_setting("poll_interval", "5")),
        "use_gemini": get_setting("use_gemini", "false") == "true",
        "gemini_api_key": masked_key
    }

@app.post("/api/config")
def update_config(data: ConfigUpdateRequest):
    print(f"API Config: Saving settings. Target: '{data.react_target}', Emojis: '{data.selected_emojis}', Randomize: {data.use_random_emoji}, Poll: {data.poll_interval}m, Gemini: {data.use_gemini}")
    save_setting("react_target", data.react_target)
    save_setting("specific_usernames", data.specific_usernames)
    save_setting("selected_emojis", data.selected_emojis)
    save_setting("use_random_emoji", "true" if data.use_random_emoji else "false")
    save_setting("poll_interval", str(data.poll_interval))
    save_setting("use_gemini", "true" if data.use_gemini else "false")
    
    # Save the Gemini API key securely in .env file instead of DB settings table
    incoming_key = data.gemini_api_key.strip()
    # If the user input is a masked value, do not overwrite the existing key
    if incoming_key and incoming_key != "••••••••":
        update_env_file("GEMINI_API_KEY", incoming_key)
        os.environ["GEMINI_API_KEY"] = incoming_key
        # Clean from database in case it was stored there previously
        save_setting("gemini_api_key", "")
    elif not incoming_key:
        update_env_file("GEMINI_API_KEY", "")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        save_setting("gemini_api_key", "")
        
    return {"status": "success", "message": "Configuration saved successfully!"}

@app.post("/api/control/start")
def start_worker():
    print("API Control: Starting background Reels monitoring...")
    res = instagram_worker.start_monitoring()
    if res["status"] == "error":
        print(f"API Control: Failed to start monitoring: {res['message']}")
        raise HTTPException(status_code=400, detail=res["message"])
    print("API Control: Background Reels monitoring started.")
    return res

@app.post("/api/control/stop")
def stop_worker():
    print("API Control: Stopping background Reels monitoring...")
    res = instagram_worker.stop_monitoring()
    print("API Control: Background Reels monitoring stopped.")
    return res

@app.post("/api/control/check-now")
def force_check_now(background_tasks: BackgroundTasks):
    """Force an immediate DM check without waiting for the poll interval."""
    print("API Control: Manual Reels check triggered.")
    if instagram_worker.status != "connected":
        print("API Control: Check aborted, Instagram worker is not connected.")
        raise HTTPException(status_code=400, detail="Not connected to Instagram.")
    background_tasks.add_task(instagram_worker._check_and_react)
    return {"status": "success", "message": "DM check triggered! Results will appear shortly."}

@app.get("/api/logs")
def fetch_logs():
    return get_logs(limit=100)

@app.post("/api/logs/clear")
def clear_logs_history():
    print("API Logs: Clearing all reaction logs from SQLite database...")
    clear_logs()
    print("API Logs: Database logs cleared successfully.")
    return {"status": "success", "message": "Reaction logs cleared."}

@app.get("/api/friends")
def get_recent_friends():
    print("API Friends: Fetching recent chat partners...")
    if instagram_worker.status != "connected":
        print("API Friends: Worker not connected to Instagram.")
        return []
    try:
        threads = instagram_worker.cl.direct_threads(amount=20)
        friends = []
        seen = set()
        for thread in threads:
            for user in thread.users:
                if user.username not in seen and user.username.lower() != instagram_worker.username.lower():
                    friends.append({"username": user.username, "full_name": user.full_name})
                    seen.add(user.username)
        print(f"API Friends: Found {len(friends)} unique recent friends.")
        return friends
    except Exception as e:
        print(f"Error fetching friends: {e}")
        return []

# Serve Frontend static assets
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

@app.get("/")
def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"detail": "Frontend assets not found. Build index.html first."}
