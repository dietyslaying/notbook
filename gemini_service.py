import yaml
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r") as f:
    prompts = yaml.safe_load(f)

client = genai.Client()

def create_document_cache(local_file_path: str, mime_type: str) -> str:
    """Uploads file and creates an explicit context cache. Returns cache ID."""
    uploaded_file = client.files.upload(file=local_file_path)
    
    cache = client.caches.create(
        model=config['llm']['model_name'],
        config=types.CreateCachedContentConfig(
            system_instruction=prompts['system_instruction'],
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=mime_type
                        )
                    ]
                )
            ],
            ttl=config['cache']['ttl'],
        )
    )
    return cache.name

def delete_document_cache(cache_name: str) -> None:
    """Explicitly deletes a cache from Google's servers to prevent billing bloat."""
    try:
        client.caches.delete(name=cache_name)
        logger.info(f"Successfully deleted cache: {cache_name}")
    except Exception as e:
        logger.warning(f"Failed to delete cache {cache_name} (it may have expired): {e}")

def generate_summary_and_suggestions(cache_name: str) -> str:
    """Generates a summary and suggested questions after document upload."""
    prompt = prompts['internal_prompts']['generate_summary_and_suggestions']
    
    try:
        response = client.models.generate_content(
            model=config['llm']['model_name'],
            contents=prompt,
            config=types.GenerateContentConfig(
                cached_content=cache_name,
                temperature=0.2, # Lower temperature for more focused summary
            )
        )
        if response.text:
            return response.text
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        
    return "Document processed successfully. What would you like to know about it?"

def query_cached_document(cache_name: str, user_question: str, chat_history: list = None) -> str:
    """Queries the specific cache ID."""
    
    contents = []
    if chat_history:
        for msg in chat_history:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["text"])]
                )
            )
            
    # Add the current user question
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_question)]
        )
    )
    
    response = client.models.generate_content(
        model=config['llm']['model_name'],
        contents=contents,
        config=types.GenerateContentConfig(
            cached_content=cache_name,
            temperature=config['llm']['temperature'],
            top_p=config['llm']['top_p'],
            top_k=config['llm']['top_k'],
            max_output_tokens=config['llm']['max_output_tokens']
        )
    )
    
    if not response.text:
        return prompts['messages']['error_not_found']
        
    return response.text
