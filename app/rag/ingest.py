"""
app/rag/ingest.py

One-time (or re-run-when-docs-change) pipeline:
    read policy .txt files -> chunk -> embed (Gemini gemini-embedding-001) -> store in ChromaDB

Run manually whenever you add/edit a file in data/policies/:
    python -m app.rag.ingest

NOTE: text-embedding-004 was deprecated (Jan 14, 2026) and the old
`google-generativeai` package is fully retired. This uses the current
`google-genai` SDK and the `gemini-embedding-001` model instead.
"""

import os
import glob
import time
from google import genai
from google.genai.types import EmbedContentConfig
from dotenv import load_dotenv

from app.rag.vectorstore import reset_policy_collection

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODEL = "gemini-embedding-001"
POLICIES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "policies")

CHUNK_SIZE_WORDS = 300    # ~400 tokens ≈ ~300 words, a safe rough conversion
CHUNK_OVERLAP_WORDS = 40  # ~50 tokens ≈ ~40 words


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """
    Simple word-based sliding-window chunker. Splits on paragraphs first
    where possible (keeps a whole idea together), falling back to a raw
    word-count window for any paragraph longer than chunk_size on its own.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_chunk_words: list[str] = []

    for para in paragraphs:
        para_words = para.split()

        if len(para_words) > chunk_size:
            if current_chunk_words:
                chunks.append(" ".join(current_chunk_words))
                current_chunk_words = []
            start = 0
            while start < len(para_words):
                end = start + chunk_size
                chunks.append(" ".join(para_words[start:end]))
                start += chunk_size - overlap
            continue

        if len(current_chunk_words) + len(para_words) <= chunk_size:
            current_chunk_words.extend(para_words)
        else:
            chunks.append(" ".join(current_chunk_words))
            overlap_words = current_chunk_words[-overlap:] if overlap else []
            current_chunk_words = overlap_words + para_words

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    return chunks


def embed_text(text: str) -> list[float]:
    """Generates an embedding vector for a chunk of text via Gemini."""
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return response.embeddings[0].values


def ingest_policies():
    print(f"Reading policy documents from: {POLICIES_DIR}")
    file_paths = sorted(glob.glob(os.path.join(POLICIES_DIR, "*.txt")))

    if not file_paths:
        raise RuntimeError(
            f"No .txt files found in {POLICIES_DIR}. "
            f"Make sure the 8 policy files are placed there first."
        )

    print(f"Found {len(file_paths)} files: {[os.path.basename(f) for f in file_paths]}")

    collection = reset_policy_collection()
    print("ChromaDB 'policies' collection reset.")

    all_ids = []
    all_embeddings = []
    all_documents = []
    all_metadatas = []

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        language = "ar" if filename.endswith("_ar.txt") else "en"

        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)
        print(f"  {filename}: {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            embedding = embed_text(chunk)
            chunk_id = f"{filename}::chunk_{i}"

            all_ids.append(chunk_id)
            all_embeddings.append(embedding)
            all_documents.append(chunk)
            all_metadatas.append({
                "source": filename,
                "language": language,
                "chunk_index": i,
            })

            # Small delay to stay comfortably within API rate limits
            # on free-tier keys — remove/reduce if you have a paid quota.
            time.sleep(0.2)

    collection.add(
        ids=all_ids,
        embeddings=all_embeddings,
        documents=all_documents,
        metadatas=all_metadatas,
    )

    print(f"\nIngested {len(all_ids)} total chunks across {len(file_paths)} files.")
    print("Done. Policy RAG store is ready.")


if __name__ == "__main__":
    ingest_policies()