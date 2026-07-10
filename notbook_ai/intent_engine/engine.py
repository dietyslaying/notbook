import google.generativeai as genai
from config import config
from interfaces import IntentType
import json
import random

class IntentEngine:
    def __init__(self):
        self.model_name = config.raw_config['llm']['model_name']

    async def classify(self, text: str) -> IntentType:
        prompt = f"""
        Classify the user's medical query into one of these intents:
        - "disease" (asking about a condition, symptoms, pathophysiology)
        - "drug" (asking about medication, dosage, side effects)
        - "comparison" (asking to compare two things)
        - "study" (asking for a quiz or flashcard)
        
        Return JSON: {{"intent": "disease"}}
        User Query: {text}
        """
        try:
            api_key = random.choice(config.gemini_api_keys) if config.gemini_api_keys else None
            if api_key:
                genai.configure(api_key=api_key)
                
            model = genai.GenerativeModel(self.model_name, generation_config={"response_mime_type": "application/json"})
            response = await model.generate_content_async(prompt)
            data = json.loads(response.text)
            return IntentType(data.get("intent", "unknown"))
        except Exception:
            return IntentType.UNKNOWN
