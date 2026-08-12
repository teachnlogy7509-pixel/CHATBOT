import json
from typing import Any
from google import genai
from google.genai import types
from config import GEMINI_MODEL

QUESTION_SCHEMA={"type":"OBJECT","properties":{
"question":{"type":"STRING"},"assertion":{"type":"STRING"},"reason":{"type":"STRING"},
"options":{"type":"ARRAY","items":{"type":"STRING"}},
"correct_option":{"type":"INTEGER"},"explanation":{"type":"STRING"}},
"required":["question","assertion","reason","options","correct_option","explanation"]}

def create_gemini_client(api_key:str): return genai.Client(api_key=api_key)

def create_question(client,topic:str,mode:str)->dict[str,Any]:
    instructions="यह सामान्य NEET Biology MCQ है।" if mode=="mcq" else "यह Assertion-Reason question है।"
    prompt=f"""आप NEET Biology expert teacher हैं।
Topic: {topic}
Question type: {mode}
{instructions}
NCERT स्तर का नया हिंदी प्रश्न बनाएं। चार options दें। correct_option 0-3 हो। छोटा explanation दें।"""
    response=client.models.generate_content(model=GEMINI_MODEL,contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json",response_schema=QUESTION_SCHEMA))
    data=json.loads(response.text)
    if len(data.get("options",[]))!=4: raise ValueError("Gemini ने 4 options नहीं दिए।")
    if int(data.get("correct_option",-1)) not in range(4): raise ValueError("गलत correct_option")
    return data

def ask_gemini(client,prompt:str)->str:
    response=client.models.generate_content(model=GEMINI_MODEL,contents=prompt)
    return (response.text or "").strip()

def solve_image_doubt(client, image_bytes: bytes, caption: str = "") -> str:
    prompt = f"आप NEET Biology expert tutor हैं। इस image में दिए गए question/doubt को हिंदी में step-by-step समझाएं। अतिरिक्त text/caption: {caption}"
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt
        ]
    )
    return (response.text or "").strip()
```[cite: 6]
