import google.generativeai as genai
from pinecone import Pinecone
from config import config
from services.cache_manager import CacheManager
from core.ndm_validator import NDMValidator
import random

class GeminiService:
    def __init__(self):
        llm_cfg = config.raw_config['llm']
        self.model_name = llm_cfg['model_name']
        self.generation_config = {
            "temperature": llm_cfg['temperature'],
            "top_p": llm_cfg['top_p'],
            "top_k": llm_cfg['top_k'],
            "max_output_tokens": llm_cfg['max_output_tokens'],
            "response_mime_type": "application/json"
        }
        
        self.pc = Pinecone(api_key=config.pinecone_api_key)
        self.pinecone_cfg = config.raw_config['pinecone']
        self.index = self.pc.Index(self.pinecone_cfg['index_name'])
        
        self.cache = CacheManager(ttl=config.raw_config['cache']['ttl'])

    async def _retrieve_context(self, query: str) -> str:
        try:
            # ZERO RAM EMBEDDINGS - RUNS ON FREE TIER
            embeddings = self.pc.inference.embed(
                model=self.pinecone_cfg['embedding_model'],
                inputs=[f"query: {query}"],
                parameters={"input_type": "query", "truncate": "END"}
            )
            vector = embeddings.data[0].values
            
            results = self.index.query(vector=vector, top_k=3, include_metadata=True)
            
            context = ""
            for match in results['matches']:
                text = match['metadata'].get('text', '')
                page = match['metadata'].get('page', 'N/A')
                context += f"Book Excerpt (Page {page}):\n{text}\n\n---\n\n"
            return context
        except Exception as e:
            print(f"Pinecone Error: {e}")
            return ""

    async def query_medical_knowledge(self, user_query: str) -> dict:
        cached = self.cache.get(user_query)
        if cached:
            return cached

        context = await self._retrieve_context(user_query)
        if not context:
            return {"error": "I couldn't find this in the medical textbooks."}

        prompt = f"""
        You are Notbook AI. Format the following textbook data strictly for a neurodivergent user (ADHD, Autism, Dyslexia).
        
        STRICT RULES:
        - NO markdown asterisks (*).
        - NO italics.
        - Summary MUST be under 3 sentences.
        - Core facts MUST be short strings (max 3).
        
        Return this exact JSON schema:
        {{
          "title": "Disease/Topic Name",
          "summary": "3 sentence max plain text summary.",
          "core_facts": ["Fact 1", "Fact 2", "Fact 3"],
          "expandable_details": "HTML formatted details using <ul><li> tags ONLY.",
          "source_citation": "Book Name, Page"
        }}
        
        TEXTBOOK CONTEXT:
        {context}
        """
        
        try:
            api_key = random.choice(config.gemini_api_keys) if config.gemini_api_keys else None
            if api_key:
                genai.configure(api_key=api_key)
                
            model = genai.GenerativeModel(self.model_name, generation_config=self.generation_config)
            response = await model.generate_content_async(prompt)
            validated_data = NDMValidator.validate(response.text)
            
            if "error" not in validated_data:
                self.cache.set(user_query, validated_data)
                
            return validated_data
        except Exception as e:
            return {"error": f"Gemini generation failed: {str(e)}"}
