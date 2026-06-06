import os
import argparse
import yaml
import logging
import pypdfium2 as pdfium
from pinecone import Pinecone, ServerlessSpec

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Load environment variables (or rely on system env)
# You should run `export PINECONE_API_KEY="..."` and `export GEMINI_API_KEY="..."` before running this
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY environment variable is missing")

pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = config['pinecone']['index_name']

def init_pinecone():
    """Initializes the Pinecone index if it doesn't exist."""
    try:
        idx_info = pc.describe_index(index_name)
        if idx_info.dimension != 1024:
            logger.info(f"Deleting incompatible index: {index_name}")
            pc.delete_index(index_name)
    except Exception:
        pass

    if index_name not in pc.list_indexes().names():
        logger.info(f"Creating Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=1024, # Dimension for multilingual-e5-large
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
    doc = pdfium.PdfDocument(pdf_path)
    full_text = ""
    for page in doc:
        textpage = page.get_textpage()
        page_text = textpage.get_text_range()
        if page_text:
            full_text += page_text + "\n"
            
    logger.info(f"Extracted {len(full_text)} characters. Chunking...")
    chunks = chunk_text(full_text)
    logger.info(f"Created {len(chunks)} chunks.")
    
    logger.info("Using Pinecone Inference API (multilingual-e5-large)...")
    batch_size = 96 # Pinecone embed accepts up to 96 inputs per request
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        logger.info(f"Embedding batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
        
        # Embed using Pinecone Inference
        response = pc.inference.embed(
            model=config['pinecone']['embedding_model'],
            inputs=batch,
            parameters={"input_type": "passage", "truncate": "END"}
        )
        embeddings = response
        
        # Prepare vectors for Pinecone
        vectors = []
        for j, embedding in enumerate(embeddings):
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
