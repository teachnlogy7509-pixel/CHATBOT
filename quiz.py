import json
from typing import Any

from google import genai
from google.genai import types


GEMINI_MODEL = "gemini-3.1-flash-lite"


QUESTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "question": {"type": "STRING"},
        "assertion": {"type": "STRING"},
        "reason": {"type": "STRING"},
        "options": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "correct_option": {"type": "INTEGER"},
        "explanation": {"type": "STRING"},
    },
    "required": [
        "question",
        "assertion",
        "reason",
        "options",
        "correct_option",
        "explanation",
    ],
}


def create_gemini_client(api_key: str):
    return genai.Client(api_key=api_key)


def create_question(client, topic: str, mode: str) -> dict[str, Any]:
    if mode == "mcq":
        instructions = (
            "यह एक सामान्य NEET Biology MCQ होना चाहिए। "
            "'question' में प्रश्न लिखें।"
        )
    else:
        instructions = (
            "यह Assertion-Reason question होना चाहिए। "
            "'assertion' और 'reason' लिखें।"
        )

    prompt = f"""
आप NEET Biology के expert teacher हैं।
Topic: {topic}
Question type: {mode}

{instructions}

NCERT स्तर का एक नया हिंदी प्रश्न बनाएं।
चार स्पष्ट options दें।
correct_option केवल 0, 1, 2 या 3 होना चाहिए।
छोटा और सही explanation दें।
उत्तर केवल दिए गए JSON schema के अनुसार दें।
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QUESTION_SCHEMA,
        ),
    )

    data = json.loads(response.text)

    if len(data.get("options", [])) != 4:
        raise ValueError("Gemini ने 4 options नहीं दिए।")

    correct = int(data.get("correct_option", -1))
    if correct not in range(4):
        raise ValueError("Gemini ने गलत correct_option दिया।")

    return data


def ask_gemini(client, prompt: str) -> str:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text.strip()
