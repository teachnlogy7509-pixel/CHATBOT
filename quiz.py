import json
import os
import google.generativeai as genai
from database import save_user, save_poll

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

async def create_question(topic: str, mode: str) -> dict:
    if mode == "mcq":
        instructions = "यह एक सामान्य NEET Biology MCQ होना चाहिए। 'question' में प्रश्न लिखें।"
    else:
        instructions = "यह Assertion-Reason question होना चाहिए। 'assertion' और 'reason' लिखें।"

    prompt = f"""
आप NEET Biology के expert teacher हैं।
Topic: {topic}
Question type: {mode}
इस topic पर NCERT लेवल का एक नया हिंदी प्रश्न बनाएं।
उत्तर केवल JSON format में दें जिसमें ये keys हों: question, assertion, reason, options (4 items की list), correct_option (0 से 3 के बीच integer), explanation।
"""

    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json", "temperature": 0.7}
    )

    data = json.loads(response.text)
    if len(data.get("options", [])) != 4:
        raise ValueError("Gemini ने 4 options नहीं दिए")
    return data

async def send_poll_logic(update, context, topic: str, mode: str):
    user = update.effective_user
    chat = update.effective_chat
    save_user(user)

    waiting_msg = await update.effective_message.reply_text(f"⏳ {topic} पर NEET प्रश्न तैयार हो रहा है...")

    try:
        data = await create_question(topic, mode)
        q_text = data.get("question") if mode == "mcq" else f"कथन (A): {data.get('assertion')}\n\nकारण (R): {data.get('reason')}"

        poll_msg = await context.bot.send_poll(
            chat_id=chat.id,
            question=q_text,
            options=data["options"],
            type="quiz",
            is_anonymous=False,
            correct_option_id=int(data["correct_option"]),
            explanation=data["explanation"]
        )

        save_poll(
            poll_id=poll_msg.poll.id,
            chat_id=chat.id,
            creator_id=user.id,
            question=q_text,
            correct_option=int(data["correct_option"]),
            explanation=data["explanation"]
        )
        await waiting_msg.delete()
    except Exception as e:
        print("Error creating question:", e)
        await waiting_msg.edit_text(f"❌ प्रश्न बनाने में त्रुटि हुई: {str(e)}")
