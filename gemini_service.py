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
    pc = None
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


def query_rag(namespace: str, user_question: str, chat_history: list = None) -> tuple[str, bool]:
    """Queries Pinecone for context and then asks Gemini to synthesise an answer.

    Returns:
        (answer_text, is_complete) — is_complete is True if Gemini finished naturally,
        False if it was cut off by the token limit.
    """
    if not index:
        return ("System error: Database not connected.", True)

    try:
        # 1. Embed the user's question
        embed_response = pc.inference.embed(
            model=config['pinecone']['embedding_model'],
            inputs=[user_question],
            parameters={"input_type": "query"}
        )
        query_embedding = embed_response[0].values

        # 2. Search Pinecone — top_k=8 gives the model more material to work with
        search_results = index.query(
            namespace=namespace,
            vector=query_embedding,
            top_k=8,
            include_metadata=True
        )

        if not search_results.matches:
            return (prompts['messages']['error_not_found'], True)

        # 3. Assemble context, filtering out very low-scoring matches (< 0.65)
        good_matches = [m for m in search_results.matches if m.score >= 0.65]
        if not good_matches:
            good_matches = search_results.matches  # fall back to all if all are low

        context_text = "\n\n---\n\n".join(
            [f"[Excerpt {i+1}]\n{m.metadata['text']}" for i, m in enumerate(good_matches)]
        )

        # 4. Build the Gemini prompt
        system_msg = prompts['system_instruction']
        full_prompt = (
            f"Here are the most relevant excerpts from the textbook:\n\n"
            f"{context_text}\n\n"
            f"---\n\nUser question: {user_question}"
        )

        contents = []
        if chat_history:
            for msg in chat_history[-6:]:  # keep last 3 turns to avoid token bloat
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

        # 5. Generate answer
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
            return (prompts['messages']['error_not_found'], True)

        # Check if Gemini finished naturally or was cut off by token limit
        is_complete = True
        try:
            finish_reason = response.candidates[0].finish_reason
            # finish_reason value 2 = MAX_TOKENS (cut off), 1 = STOP (natural end)
            is_complete = str(finish_reason) in ("FinishReason.STOP", "STOP", "1")
        except Exception:
            pass  # if we can't check, assume complete

        return (response.text, is_complete)

    except Exception as e:
        logger.error(f"RAG Inference failed: {e}")
        raise e

