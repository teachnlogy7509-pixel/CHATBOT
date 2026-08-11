import os
from google import genai
from telegram import Update
from telegram.ext import Application

from bot import register_handlers, restore_schedules
from database import setup_database

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN missing")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

def main():
    setup_database()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.bot_data["gemini_client"] = genai.Client(api_key=GEMINI_API_KEY)
    register_handlers(app)
    restore_schedules(app)
    print("🚀 NEET Gemini Bot Started Successfully!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
