import os
import yaml
import logging
from google import genai
from google.genai import types
from pinecone import Pinecone

logger = logging.getLogger(__name__)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r") as f:
    prompts = yaml.safe_load(f)

client = genai.Client()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if PINECONE_API_KEY:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(config['pinecone']['index_name'])
else:
    logger.warning("PINECONE_API_KEY not found in environment!")
    index = None

def get_available_books() -> list:
    """Fetches namespaces from Pinecone to populate the library menu."""
    if not index:
        return []
    try:
        stats = index.describe_index_stats()
        namespaces = stats.get("namespaces", {})
        return list(namespaces.keys())
    except Exception as e:
        logger.error(f"Failed to fetch Pinecone namespaces: {e}")
        return []

def query_rag(namespace: str, user_question: str, chat_history: list = None) -> str:
    """Queries Pinecone for context and then asks Gemini."""
    if not index:
        return "System error: Database not connected."
        
    try:
        # 1. Embed the user's question
        embed_response = client.models.embed_content(
            model=config['pinecone']['embedding_model'],
            contents=user_question
        )
        query_embedding = embed_response.embeddings[0].values
        
        # 2. Search Pinecone for top 5 relevant chunks
        search_results = index.query(
            namespace=namespace,
            vector=query_embedding,
            top_k=5,
            include_metadata=True
        )
        
        if not search_results.matches:
            return prompts['messages']['error_not_found']
            
        # 3. Assemble the retrieved context
        context_text = "\n\n---\n\n".join([match.metadata["text"] for match in search_results.matches])
        
        # 4. Construct prompt for Gemini
        system_msg = prompts['system_instruction']
        
        full_prompt = f"Here is the retrieved context from the document:\n{context_text}\n\nUser Question: {user_question}"
        
        contents = []
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
                parts=[types.Part.from_text(text=full_prompt)]
            )
        )
        
        # 5. Generate final answer
        response = client.models.generate_content(
            model=config['llm']['model_name'],
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_msg,
                temperature=config['llm']['temperature'],
                top_p=config['llm']['top_p'],
                top_k=config['llm']['top_k'],
                max_output_tokens=config['llm']['max_output_tokens']
            )
        )
        
        if not response.text:
            return prompts['messages']['error_not_found']
            
        return response.text
        
    except Exception as e:
        logger.error(f"RAG Inference failed: {e}")
        raise e
