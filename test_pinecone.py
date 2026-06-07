import os
from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

try:
    embeddings = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=["Hello world"],
        parameters={"input_type": "query"}
    )
    print("SUCCESS")
    print(len(embeddings[0].values))
except Exception as e:
    print("FAILED:", e)
