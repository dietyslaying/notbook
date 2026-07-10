import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def main():
    import gemini_service
    
    query = "Tell me about asthma"
    namespace = "global|murtaghs"
    
    # 1. Embed the user's question
    print("Embedding query...")
    query_embedding = gemini_service.pc.inference.embed(
        model=gemini_service.config['pinecone']['embedding_model'],
        inputs=[query],
        parameters={"input_type": "query"}
    )[0].values

    # 2. Search Pinecone
    print("Searching Pinecone...")
    search_results = gemini_service.index.query(
        namespace=namespace,
        vector=query_embedding,
        top_k=12,
        include_metadata=True
    )
    
    print(f"Total matches found: {len(search_results.matches)}")
    for i, m in enumerate(search_results.matches):
        print(f"Match {i+1}: Score = {m.score}, Page = {m.metadata.get('page')}")
        print(f"Text snippet: {m.metadata.get('text', '')[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())
