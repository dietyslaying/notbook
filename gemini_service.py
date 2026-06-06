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
    """Uploads file and attempts to create an explicit context cache.
    Falls back to raw file mode if the document is too small or cache is not supported."""
    uploaded_file = client.files.upload(file=local_file_path)
    
    try:
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
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception as fe:
            logger.warning(f"Could not delete temp file {uploaded_file.name} after caching: {fe}")
            
        return f"cache|{cache.name}"
    except Exception as e:
        logger.info(f"Failed to create cache: {e}. Using raw file fallback.")
        return f"file|{uploaded_file.name}|{uploaded_file.uri}|{mime_type}"

def delete_document_cache(session_info: str) -> None:
    """Explicitly deletes the cache or the file from Google's servers."""
    if not session_info:
        return
        
    delimiter = "|" if "|" in session_info else ":"
    parts = session_info.split(delimiter)
    mode = parts[0]
    
    if mode == "cache":
        cache_name = session_info.split(delimiter, 1)[1]
        try:
            client.caches.delete(name=cache_name)
            logger.info(f"Successfully deleted cache: {cache_name}")
        except Exception as e:
            logger.warning(f"Failed to delete cache {cache_name} (it may have expired): {e}")
    elif mode == "file":
        if len(parts) >= 2:
            file_name = parts[1]
            try:
                client.files.delete(name=file_name)
                logger.info(f"Successfully deleted file: {file_name}")
            except Exception as e:
                logger.warning(f"Failed to delete file {file_name} (it may have expired): {e}")

def generate_summary_and_suggestions(session_info: str) -> str:
    """Generates a summary and suggested questions after document upload."""
    prompt = prompts['internal_prompts']['generate_summary_and_suggestions']
    delimiter = "|" if "|" in session_info else ":"
    parts = session_info.split(delimiter)
    mode = parts[0]
    
    try:
        if mode == "cache":
            cache_name = session_info.split(delimiter, 1)[1]
            response = client.models.generate_content(
                model=config['llm']['model_name'],
                contents=prompt,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=0.2,
                )
            )
        else:
            file_uri = session_info.split(delimiter, 3)[2]
            mime_type = session_info.split(delimiter, 3)[3]
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(file_uri=file_uri, mime_type=mime_type),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ]
            response = client.models.generate_content(
                model=config['llm']['model_name'],
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=prompts['system_instruction'],
                    temperature=0.2,
                )
            )
            
        if response.text:
            return response.text
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        
    return "Document processed successfully. What would you like to know about it?"

def query_cached_document(session_info: str, user_question: str, chat_history: list = None) -> str:
    """Queries either the explicit cache or the raw file based on the session type."""
    delimiter = "|" if "|" in session_info else ":"
    parts = session_info.split(delimiter)
    mode = parts[0]
    
    contents = []
    
    if mode == "cache":
        cache_name = session_info.split(delimiter, 1)[1]
        if chat_history:
            for msg in chat_history:
                contents.append(
                    types.Content(
                        role=msg["role"],
                        parts=[types.Part.from_text(text=msg["text"])]
                    )
                )
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
    else:
        file_uri = session_info.split(delimiter, 3)[2]
        mime_type = session_info.split(delimiter, 3)[3]
        
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(file_uri=file_uri, mime_type=mime_type),
                    types.Part.from_text(text="[Document Uploaded]")
                ]
            )
        )
        contents.append(
            types.Content(
                role="model",
                parts=[types.Part.from_text(text="I have received the document and am ready to answer your questions.")]
            )
        )
        
        if chat_history:
            for msg in chat_history:
                contents.append(
                    types.Content(
                        role=msg["role"],
                        parts=[types.Part.from_text(text=msg["text"])]
                    )
                )
                
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
                system_instruction=prompts['system_instruction'],
                temperature=config['llm']['temperature'],
                top_p=config['llm']['top_p'],
                top_k=config['llm']['top_k'],
                max_output_tokens=config['llm']['max_output_tokens']
            )
        )
        
    if not response.text:
        return prompts['messages']['error_not_found']
        
    return response.text
