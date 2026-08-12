from telegram import Update
from telegram.ext import Application
from config import TELEGRAM_TOKEN,GEMINI_API_KEY
from quiz import create_gemini_client
from database import setup_database
from bot import register_handlers,restore_schedules

def main():
    setup_database()
    app=Application.builder().token(TELEGRAM_TOKEN).build()
    app.bot_data["gemini_client"]=create_gemini_client(GEMINI_API_KEY)
    register_handlers(app)
    restore_schedules(app)
    print("🚀 NEET Gemini Bot Started Successfully!")
    app.run_polling(allowed_updates=Update.ALL_TYPES,drop_pending_updates=True)

if __name__=="__main__":
    main()
