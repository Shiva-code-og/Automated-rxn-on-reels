import sys
import os
import subprocess
import importlib

# Force UTF-8 encoding on Windows to prevent emoji/unicode crashes
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"

def install_requirements():
    print("Checking application dependencies...")
    requirements = ["fastapi", "uvicorn", "instagrapi", "pydantic"]
    missing = []
    for req in requirements:
        try:
            importlib.import_module(req)
        except ImportError:
            missing.append(req)
            
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}. Installing via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("Dependencies successfully installed!")
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)
    else:
        print("All dependencies are already installed.")

if __name__ == "__main__":
    install_requirements()
    
    print("Starting Automated Reels Reaction Backend...")
    print("Dashboard: http://127.0.0.1:8000")
    import uvicorn
    # Start uvicorn server (access_log=False to hide the constant local dashboard GET polling logs)
    # We restrict reload_dirs to backend/frontend so database (.db), session (.json) and env (.env) file updates do not trigger server restarts.
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True, reload_dirs=["backend", "frontend"], access_log=False)
