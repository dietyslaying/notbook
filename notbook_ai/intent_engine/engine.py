import google.generativeai as genai
from config import config
from interfaces import IntentType
import json

class IntentEngine:
    def __init__(self):
        genai.configure(api_key=config.gemini_api_key)
        self.model = genai.GenerativeModel(
            config.raw_config['llm']['model_name'],
            generation_config={"response_mime_type": "application/json"}
        )

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
            response = await self.model.generate_content_async(prompt)
            data = json.loads(response.text)
            return IntentType(data.get("intent", "unknown"))
        except Exception:
            return IntentType.UNKNOWN
