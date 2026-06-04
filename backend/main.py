from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(ENV_PATH)

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback-insecure-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

from .database import get_setting, save_setting, get_all_settings, get_logs, clear_logs
from .instagram_worker import worker_manager

app = FastAPI(title="Automated Reels Reaction API - SaaS Edition")

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"An internal server error occurred: {str(exc)}"}
    )

class LoginRequest(BaseModel):
    username: str
    password: str

class TwoFactorRequest(BaseModel):
    code: str
    username: str # Pass username to link the 2FA flow

class ConfigUpdateRequest(BaseModel):
    react_target: str
    specific_usernames: str
    selected_emojis: str
    use_random_emoji: bool
    poll_interval: int
    use_gemini: bool
    gemini_api_key: str

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

@app.on_event("startup")
def startup_event():
    print("SaaS Backend Starting... Background workers will initialize lazily when users connect.")

@app.get("/api/status")
def get_status(user_id: str = Depends(get_current_user)):
    worker = worker_manager.get_worker(user_id)
    logs_count = len(get_logs(user_id, limit=10000))
    
    return {
        "status": worker.status,
        "username": user_id,
        "error_message": worker.error_message,
        "is_running": worker.is_worker_running(),
        "logs_count": logs_count
    }

@app.post("/api/login")
def login(data: LoginRequest, background_tasks: BackgroundTasks):
    user_id = data.username.lower()
    print(f"[{user_id}] API Login: Attempting connection...")
    
    worker = worker_manager.get_worker(user_id)
    res = worker.login(data.username, data.password)
    
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
        
    if res["status"] == "success":
        access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        access_token = create_access_token(
            data={"sub": user_id}, expires_delta=access_token_expires
        )
        res["token"] = access_token
        
    return res

@app.post("/api/login/2fa")
def login_2fa(data: TwoFactorRequest):
    user_id = data.username.lower()
    print(f"[{user_id}] API Login 2FA: Submitting code...")
    
    worker = worker_manager.get_worker(user_id)
    res = worker.login_2fa(data.code)
    
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
        
    if res["status"] == "success":
        access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        access_token = create_access_token(
            data={"sub": user_id}, expires_delta=access_token_expires
        )
        res["token"] = access_token
        
    return res

@app.post("/api/logout")
def logout(user_id: str = Depends(get_current_user)):
    print(f"[{user_id}] API Logout: Disconnecting Instagram account...")
    worker = worker_manager.get_worker(user_id)
    worker.stop_monitoring()
    res = worker.logout()
    worker_manager.remove_worker(user_id)
    return res

@app.get("/api/config")
def get_config(user_id: str = Depends(get_current_user)):
    api_key = get_setting(user_id, "gemini_api_key", "")
    masked_key = "••••••••" if api_key else ""
    return {
        "react_target": get_setting(user_id, "react_target", "all"),
        "specific_usernames": get_setting(user_id, "specific_usernames", ""),
        "selected_emojis": get_setting(user_id, "selected_emojis", "❤️,🔥,😂,😮,👏"),
        "use_random_emoji": get_setting(user_id, "use_random_emoji", "false") == "true",
        "poll_interval": int(get_setting(user_id, "poll_interval", "5")),
        "use_gemini": get_setting(user_id, "use_gemini", "false") == "true",
        "gemini_api_key": masked_key
    }

@app.post("/api/config")
def update_config(data: ConfigUpdateRequest, user_id: str = Depends(get_current_user)):
    save_setting(user_id, "react_target", data.react_target)
    save_setting(user_id, "specific_usernames", data.specific_usernames)
    save_setting(user_id, "selected_emojis", data.selected_emojis)
    save_setting(user_id, "use_random_emoji", "true" if data.use_random_emoji else "false")
    save_setting(user_id, "poll_interval", str(data.poll_interval))
    save_setting(user_id, "use_gemini", "true" if data.use_gemini else "false")
    
    incoming_key = data.gemini_api_key.strip()
    if incoming_key and incoming_key != "••••••••":
        save_setting(user_id, "gemini_api_key", incoming_key)
    elif not incoming_key:
        save_setting(user_id, "gemini_api_key", "")
        
    return {"status": "success", "message": "Configuration saved successfully!"}

@app.post("/api/control/start")
def start_worker(user_id: str = Depends(get_current_user)):
    worker = worker_manager.get_worker(user_id)
    res = worker.start_monitoring()
    if res["status"] == "error":
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/control/stop")
def stop_worker(user_id: str = Depends(get_current_user)):
    worker = worker_manager.get_worker(user_id)
    res = worker.stop_monitoring()
    return res

@app.post("/api/control/check-now")
def force_check_now(background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user)):
    worker = worker_manager.get_worker(user_id)
    if worker.status != "connected":
        raise HTTPException(status_code=400, detail="Not connected to Instagram.")
    background_tasks.add_task(worker._check_and_react)
    return {"status": "success", "message": "DM check triggered! Results will appear shortly."}

@app.get("/api/logs")
def fetch_logs(user_id: str = Depends(get_current_user)):
    return get_logs(user_id, limit=100)

@app.post("/api/logs/clear")
def clear_logs_history(user_id: str = Depends(get_current_user)):
    clear_logs(user_id)
    return {"status": "success", "message": "Reaction logs cleared."}

@app.get("/api/friends")
def get_recent_friends(user_id: str = Depends(get_current_user)):
    worker = worker_manager.get_worker(user_id)
    if worker.status != "connected":
        return []
    try:
        threads = worker.cl.direct_threads(amount=20)
        friends = []
        seen = set()
        for thread in threads:
            for user in thread.users:
                if user.username not in seen and user.username.lower() != user_id:
                    friends.append({"username": user.username, "full_name": user.full_name})
                    seen.add(user.username)
        return friends
    except Exception as e:
        print(f"Error fetching friends: {e}")
        return []

if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

@app.get("/")
def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"detail": "Frontend assets not found. Build index.html first."}
