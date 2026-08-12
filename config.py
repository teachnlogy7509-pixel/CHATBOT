import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite"
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_FILE = os.getenv("DB_FILE", "bot_data.db")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN missing")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")
