import os
import yaml
import logging
from google import genai
from google.genai import types
from pinecone import Pinecone

logger = logging.getLogger(__name__)

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open("prompts.yaml", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

api_keys_str = os.getenv("GEMINI_API_KEYS", "")
api_keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]

if not api_keys:
    clients = [genai.Client()]
else:
    clients = [genai.Client(api_key=key) for key in api_keys]
current_client_idx = 0

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if PINECONE_API_KEY:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(config['pinecone']['index_name'])
else:
    logger.warning("PINECONE_API_KEY not found in environment!")
    pc = None
    index = None


def get_available_books(user_id: int = None) -> list:
    """Fetches namespaces from Pinecone to populate the library menu.
    Returns: list of (namespace, display_name)"""
    if not index:
        return []
    try:
        stats = index.describe_index_stats()
        namespaces = stats.get("namespaces", {})
        
        books = []
        user_prefix = f"{user_id}|" if user_id else None
        
        for ns in namespaces.keys():
            if ns.startswith("_"):
                continue
                
            if user_prefix and ns.startswith(user_prefix):
                books.append((ns, ns[len(user_prefix):]))
            elif ns.startswith("global|"):
                books.append((ns, ns[len("global|"):]))
            elif "|" not in ns:
                # Legacy un-prefixed namespaces are global
                books.append((ns, ns))
                
        return books
    except Exception as e:
        logger.error(f"Failed to fetch Pinecone namespaces: {e}")
        return []


async def query_rag_stream(namespace: str, user_question: str, chat_history: list = None, mode: str = "chat"):
    import asyncio
    if not index:
        yield ("System error: Database not connected.", True)
        return

    try:
        # 1. Embed the user's question
        def _embed():
            return pc.inference.embed(
                model=config['pinecone']['embedding_model'],
                inputs=[user_question],
                parameters={"input_type": "query"}
            )[0].values
        query_embedding = await asyncio.to_thread(_embed)

        # 2. Search Pinecone
        def _search():
            return index.query(
                namespace=namespace,
                vector=query_embedding,
                top_k=12,
                include_metadata=True
            )
        search_results = await asyncio.to_thread(_search)

        if not search_results.matches:
            yield (prompts['messages']['error_not_found'], True)
            return

        # 3. Quality filter
        good_matches = [m for m in search_results.matches if m.score >= 0.70]
        if len(good_matches) < 3:
            good_matches = [m for m in search_results.matches if m.score >= 0.60]

        if not good_matches:
            yield (prompts['messages']['error_not_found'], True)
            return

        # 4. Construct context
        context_text = ""
        for m in good_matches:
            meta = m.metadata
            page = meta.get('page', 'Unknown')
            text = meta.get('text', '')
            context_text += f"[Page {page}]\n{text}\n\n"

        system_msg = prompts['system_instruction']
        mode_instruction = prompts.get('modes', {}).get(mode, "")
        if mode_instruction:
            system_msg += "\n\n" + str(mode_instruction)

        contents = []
        if chat_history:
            for msg in chat_history[-6:]:
                role = "user" if msg['role'] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg['text'])]))

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=f"Question: {user_question}\n\nRelevant Excerpts from textbook:\n{context_text}")]
            )
        )

        from knowledge_tree import KnowledgeDocument
        
        config_kwargs = {
            "system_instruction": system_msg,
            "temperature": config['llm']['temperature'],
            "top_p": config['llm']['top_p'],
            "top_k": config['llm']['top_k'],
            "max_output_tokens": config['llm']['max_output_tokens'],
        }
        
        if mode not in ("quiz", "flashcards"):
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = KnowledgeDocument
            
        gemini_config = types.GenerateContentConfig(**config_kwargs)

        global current_client_idx
        max_gemini_retries = len(clients)
        
        for attempt in range(max_gemini_retries):
            client = clients[current_client_idx]
            try:
                response_stream = await client.aio.models.generate_content_stream(
                    model=config['llm']['model_name'],
                    contents=contents,
                    config=gemini_config
                )
                
                async for chunk in response_stream:
                    if chunk.text:
                        is_complete = None
                        if chunk.candidates and chunk.candidates[0].finish_reason:
                            fr = str(chunk.candidates[0].finish_reason)
                            if fr not in ("FinishReason.FINISH_REASON_UNSPECIFIED", "0", "None", "", "Unspecified"):
                                is_complete = fr in ("FinishReason.STOP", "STOP", "1")
                        yield (chunk.text, is_complete)
                        
                break # Success, exit retry loop
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    logger.warning(f"Client {current_client_idx} rate limited. Rotating key...")
                    current_client_idx = (current_client_idx + 1) % len(clients)
                    if attempt == max_gemini_retries - 1:
                        raise RuntimeError("RATE_LIMIT_EXCEEDED")
                else:
                    raise

    except Exception as e:
        logger.error(f"RAG Inference failed: {e}")
        raise e
