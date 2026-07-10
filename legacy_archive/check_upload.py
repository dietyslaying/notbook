from pinecone import Pinecone
import pypdfium2 as pdfium
import os

pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
index = pc.Index('library-index')
stats = index.describe_index_stats()

print('=== PINECONE INDEX STATS ===')
print(f'Total vectors in index: {stats["total_vector_count"]}')
for ns, data in stats.get('namespaces', {}).items():
    print(f'  Namespace "{ns}": {data["vector_count"]} vectors')

print()
print('=== PDF PAGE COUNT ===')
pdf_path = r'C:\Users\kim\Documents\Crore\dokumen.pub_murtaghs-general-practice-8nbsped (1)-2.pdf'
doc = pdfium.PdfDocument(pdf_path)
total_pages = len(doc)
print(f'Total pages in PDF: {total_pages}')

# Also count non-empty pages
non_empty = 0
for page in doc:
    tp = page.get_textpage()
    if tp.get_text_range().strip():
        non_empty += 1
print(f'Non-empty pages: {non_empty}')
print(f'Blank/image-only pages: {total_pages - non_empty}')
