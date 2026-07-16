"""
DEPRECATED test harness — do NOT hardcode secrets here.

Use environment variables:
  PINECONE_API_KEY, GEMINI_API_KEY

This file is kept only as a stub so old docs do not reintroduce leaked keys.
"""

import os
import sys

print(
    "scratch_test.py is disabled. "
    "Use the active app under main.py + notbook_ai/.\n"
    f"PINECONE set: {bool(os.getenv('PINECONE_API_KEY'))}\n"
    f"GEMINI set: {bool(os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEYS'))}"
)
sys.exit(1)
