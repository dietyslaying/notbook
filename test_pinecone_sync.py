import yaml
from pinecone import Pinecone
from dotenv import load_dotenv
import os

load_dotenv()
config = yaml.safe_load(open('config.yaml'))
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
index = pc.Index(config['pinecone']['index_name'])

query = "asthma"
namespace = "General Practice"

# 1. Embed the user's question
print("Embedding query...")
query_embedding = pc.inference.embed(
    model=config['pinecone']['embedding_model'],
    inputs=[query],
    parameters={"input_type": "query"}
)[0].values

# 2. Search Pinecone
print("Searching Pinecone...")
search_results = index.query(
    namespace=namespace,
    vector=query_embedding,
    top_k=12,
    include_metadata=True
)

print(f"Total matches found: {len(search_results.matches)}")
for i, m in enumerate(search_results.matches):
    print(f"Match {i+1}: Score = {m.score}, Page = {m.metadata.get('page')}")
