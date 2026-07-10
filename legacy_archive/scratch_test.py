import os
import yaml
import gemini_service

os.environ['PINECONE_API_KEY'] = '***REMOVED_PINECONE***'
os.environ['GEMINI_API_KEY'] = '***REMOVED_GEMINI***'

print("Available books:", gemini_service.get_available_books())

print("Testing RAG Query on 'General Practice'...")
import pinecone
from pinecone import Pinecone
pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
response = pc.inference.embed(model='multilingual-e5-large', inputs=["What is the recommended treatment for essential hypertension?"], parameters={"input_type": "query"})
query_embedding = response[0].values
index = pc.Index("library-index")
search_results = index.query(namespace="General Practice", vector=query_embedding, top_k=3, include_metadata=True)
for i, match in enumerate(search_results.matches):
    print(f"\n--- MATCH {i+1} (score: {match.score}) ---")
    print(match.metadata.get("text", "")[:500])

print("\nCalling Gemini...")
answer = gemini_service.query_rag("General Practice", "What is the recommended treatment for essential hypertension?")
print("Answer:", answer)
