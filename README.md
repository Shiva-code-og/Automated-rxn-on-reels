# AutoReact - Instagram Reels Automated Reaction Tool 🚀

AutoReact is a modern, premium web-based dashboard and automated background worker that monitors incoming Instagram Direct Messages (DMs) for shared Reels. It analyzes the content and sentiment using Google Gemini AI and automatically reacts with the most contextually appropriate emoji.

---

## ✨ Features

- **🧠 Gemini AI Sentiment Analysis:** Uses the state-of-the-art `gemini-2.5-flash` model to analyze Reel captions, direct message contexts, and up to 30 comments to select the most fitting reaction emoji.
- **💬 Comments Processing:** Automatically fetches 20–30 comments per Reel using the Instagram API to construct an accurate sentiment profile.
- **🛡️ Secure API Key Management:** Users configure their own Gemini API keys via the dashboard. Keys are securely stored in a local SQLite database and masked in the UI (`••••••••`).
- **🎨 Premium Glassmorphism Dashboard:** Responsive, beautifully designed dark-mode web interface to connect your Instagram account, track worker status, view real-time reaction logs, and adjust settings.
- **🎯 Targeted Reactions (Friend Selector):** Dynamically fetches your recent chat partners from DMs into an interactive, clickable grid so you can selectively target only specific friends for automated reactions.
- **⚡ Smart Fallback:** If Gemini is disabled or the API key is not configured, the system automatically falls back to an advanced local keyword-based sentiment analyzer.
- **🔕 Quiet Terminal Logging:** Configured to prevent uvicorn access log spamming, so you only see actual Reel checks and reaction events in the console.

---

## 🛠️ Tech Stack

- **Backend:** FastAPI (Python), Uvicorn, Instagrapi (Instagram Private API wrapper), SQLite (Local data storage), Pydantic
- **Frontend:** Vanilla HTML5, CSS3 (Glassmorphism design system), JavaScript (ES6+, real-time polling)

---

## 🚀 Getting Started

### 📋 Prerequisites

Make sure you have **Python 3.10+** installed on your system.

### 📥 Installation & Setup

1. **Clone the Repository:**
   ```bash
   git clone <your-repository-url>
   cd "Automated rxn on reels"
   ```

2. **Set Up a Virtual Environment (Recommended):**
   * **Windows:**
     ```bash
     python -m venv venv
     .\venv\Scripts\activate
     ```
   * **Mac/Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Application:**
   ```bash
   python run.py
   ```

5. **Access the Dashboard:**
   Open your browser and navigate to:
   ```text
   http://127.0.0.1:8000
   ```

---

## ⚙️ Configuration & Usage

1. **Connect Instagram:**
   * Enter your Instagram credentials on the dashboard login screen.
   * *Note: AutoReact saves your login session securely into the local database to prevent repeated logins.*

2. **Configure Gemini AI:**
   * Obtain a free Gemini API Key from the **[Google AI Studio](https://aistudio.google.com/)**.
   * On the dashboard settings panel, check **Enable Gemini AI Analysis**.
   * Paste your API Key (which starts with `AIzaSy`) and click **Save Settings**.
   * *Note: Your key is stored securely in the local `.db` file and is never exposed.*

3. **Start Monitoring:**
   * Click **Start Monitor** in the Control Center to begin checking for shared Reels.
   * You can adjust the **Polling Interval** slider (safe mode: 5+ minutes to avoid Instagram rate limits).
   * Click **Check Now** to trigger an immediate, manual inbox check.

---

## 🔒 Security Best Practices

To protect your credentials, this repository is configured with a `.gitignore` file that automatically excludes the following sensitive files from being pushed to Git:
- **`.env`** (contains your global secrets)
- **`*.db`** (local SQLite databases containing reaction logs, API keys, and encrypted Instagram login session cookies)

*Never share your `.env` or `.db` files with anyone.*
