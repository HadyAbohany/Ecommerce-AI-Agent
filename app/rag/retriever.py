"""
app/rag/retriever.py

Hybrid retrieval for the policy RAG: combines BM25 keyword search with
semantic (embedding) search, then reranks the combined candidates with
a cross-encoder for final relevance ordering.

Pipeline:
    query -> BM25 top-k  ─┐
                           ├─> union of candidates -> cross-encoder rerank -> final top-k
    query -> semantic top-k ┘

Usage:
    from app.rag.retriever import search_policy
    results = search_policy("How long do I have to return a product?")
"""

import os
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from google import genai
from google.genai.types import EmbedContentConfig
from dotenv import load_dotenv

from app.rag.vectorstore import get_policy_collection

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=GEMINI_API_KEY)
EMBEDDING_MODEL = "gemini-embedding-001"

# Standard, lightweight cross-encoder — good relevance/speed tradeoff,
# widely used as a solid default for reranking tasks.
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

BM25_CANDIDATES = 8    # how many candidates BM25 contributes
SEMANTIC_CANDIDATES = 8  # how many candidates semantic search contributes

# ── Lazy-loaded singletons ──────────────────────────────────────────
_bm25_index = None
_bm25_corpus_ids = None       # parallel list: chunk id per BM25 doc position
_bm25_corpus_texts = None     # parallel list: chunk text per BM25 doc position
_bm25_corpus_metadatas = None # parallel list: metadata per BM25 doc position
_reranker = None


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer — works reasonably for both Arabic and English."""
    return text.lower().split()


def _build_bm25_index():
    """
    Pulls every chunk out of the ChromaDB collection once, and builds an
    in-memory BM25 index over them. Cached at module level so this only
    runs once per process, not once per query.
    """
    global _bm25_index, _bm25_corpus_ids, _bm25_corpus_texts, _bm25_corpus_metadatas

    collection = get_policy_collection()
    all_data = collection.get(include=["documents", "metadatas"])

    _bm25_corpus_ids = all_data["ids"]
    _bm25_corpus_texts = all_data["documents"]
    _bm25_corpus_metadatas = all_data["metadatas"]

    tokenized_corpus = [_tokenize(doc) for doc in _bm25_corpus_texts]
    _bm25_index = BM25Okapi(tokenized_corpus)


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL_NAME)
    return _reranker


def _embed_query(text: str) -> list[float]:
    """Embeds a user question for semantic search (RETRIEVAL_QUERY task type,
    distinct from RETRIEVAL_DOCUMENT used at ingest time — this asymmetry is
    intentional and recommended by Gemini's embedding API for retrieval use cases)."""
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return response.embeddings[0].values


def _bm25_search(query: str, top_k: int) -> list[dict]:
    if _bm25_index is None:
        _build_bm25_index()

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)

    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    return [
        {
            "id": _bm25_corpus_ids[i],
            "text": _bm25_corpus_texts[i],
            "metadata": _bm25_corpus_metadatas[i],
        }
        for i in ranked_indices
        if scores[i] > 0  # skip zero-score (no keyword overlap at all) results
    ]


def _semantic_search(query: str, top_k: int) -> list[dict]:
    collection = get_policy_collection()
    query_embedding = _embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas"],
    )

    return [
        {
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
        }
        for i in range(len(results["ids"][0]))
    ]


def search_policy(question: str, top_k: int = 3) -> list[dict]:
    """
    Hybrid search over the policy knowledge base.

    Returns the top_k most relevant chunks, each as:
        {"text": "...", "source": "shipping_policy_en.txt", "language": "en", "score": 0.87}

    score is the cross-encoder relevance score (higher = more relevant),
    not a probability — useful for comparative ranking, not calibrated confidence.
    """
    if _bm25_index is None:
        _build_bm25_index()

    bm25_results = _bm25_search(question, BM25_CANDIDATES)
    semantic_results = _semantic_search(question, SEMANTIC_CANDIDATES)

    # Merge candidates, de-duplicating by chunk id (a chunk found by both
    # methods should only be reranked once).
    combined = {}
    for r in bm25_results + semantic_results:
        combined[r["id"]] = r

    candidates = list(combined.values())
    if not candidates:
        return []

    reranker = _get_reranker()
    pairs = [(question, c["text"]) for c in candidates]
    scores = reranker.predict(pairs)

    scored_candidates = list(zip(candidates, scores))
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    top_results = scored_candidates[:top_k]

    return [
        {
            "text": c["text"],
            "source": c["metadata"]["source"],
            "language": c["metadata"]["language"],
            "score": float(score),
        }
        for c, score in top_results
    ]
