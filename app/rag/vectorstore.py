"""
app/rag/vectorstore.py

Shared ChromaDB client/collection setup — the RAG equivalent of
app/db/database.py. ingest.py and retriever.py both import
get_policy_collection() from here instead of creating their own
client, so there's only one place that knows about storage location,
collection name, etc.

NOTE ON EMBEDDINGS: we do NOT attach a Chroma "embedding_function"
here. Embeddings are generated explicitly in ingest.py (when storing)
and retriever.py (when querying) using Gemini's text-embedding-004,
and passed in directly as vectors. This keeps the embedding logic in
one visible place per operation, rather than hidden inside a Chroma
wrapper class — easier to debug and to swap models later if needed.
"""

import os
import chromadb

# Persistent local storage — add "chroma_db/" to .gitignore.
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
COLLECTION_NAME = "policies"

_client = None
_collection = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Returns a singleton persistent ChromaDB client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
    return _client


def get_policy_collection():
    """
    Returns the 'policies' collection, creating it if it doesn't exist yet.
    This is the single entry point ingest.py and retriever.py should use.
    """
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # cosine similarity, standard for text embeddings
        )
    return _collection


def reset_policy_collection():
    """
    Deletes and recreates the 'policies' collection from scratch.
    Called by ingest.py at the start of every ingestion run, so that
    re-running ingestion after editing a policy doc never leaves stale
    duplicate chunks behind (same pattern as build_database.py dropping
    and recreating SQL tables).
    """
    global _collection
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # collection may not exist yet on first run — fine to ignore
    _collection = None
    return get_policy_collection()
