import os
import argparse
import yaml
import logging
from pypdf import PdfReader
from pinecone import Pinecone, ServerlessSpec
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Load environment variables (or rely on system env)
# You should run `export PINECONE_API_KEY="..."` and `export GEMINI_API_KEY="..."` before running this
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY environment variable is missing")

client = genai.Client()
pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = config['pinecone']['index_name']

def init_pinecone():
    """Initializes the Pinecone index if it doesn't exist."""
    if index_name not in pc.list_indexes().names():
        logger.info(f"Creating Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=768, # Dimension for text-embedding-004
            metric='cosine',
            spec=ServerlessSpec(
                cloud='aws',
                region='us-east-1' # Default free tier region
            )
        )
    return pc.Index(index_name)

def chunk_text(text: str, max_chunk_size: int = 1000, overlap: int = 200):
    """Splits text into chunks with overlap to maintain context."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += max_chunk_size - overlap
    return chunks

def ingest_pdf(pdf_path: str, namespace: str):
    index = init_pinecone()
    
    logger.info(f"Reading PDF: {pdf_path}")
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"
            
    logger.info(f"Extracted {len(full_text)} characters. Chunking...")
    chunks = chunk_text(full_text)
    logger.info(f"Created {len(chunks)} chunks.")
    
    batch_size = 100 # Process in batches to avoid API limits
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        logger.info(f"Embedding batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
        
        # Embed with Gemini
        response = client.models.embed_content(
            model=config['pinecone']['embedding_model'],
            contents=batch
        )
        
        # Prepare vectors for Pinecone
        vectors = []
        for j, embedding in enumerate(response.embeddings):
            chunk_idx = i + j
            vector_id = f"chunk_{chunk_idx}"
            metadata = {
                "text": batch[j],
                "source": os.path.basename(pdf_path)
            }
            vectors.append({
                "id": vector_id,
                "values": embedding.values,
                "metadata": metadata
            })
            
        # Upsert to Pinecone
        index.upsert(vectors=vectors, namespace=namespace)
        
    logger.info(f"Successfully ingested {pdf_path} into namespace '{namespace}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest a PDF into Pinecone for RAG.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("book_name", help="Name of the book (used as the Pinecone namespace)")
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        logger.error(f"File not found: {args.pdf_path}")
        exit(1)
        
    ingest_pdf(args.pdf_path, args.book_name)
