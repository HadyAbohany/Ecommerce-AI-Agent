# E-commerce AI Agent

A multi-channel AI agent for online stores — not just a chatbot that answers questions, but an agent that can **look up real product/order data, search store policies, and take actions like placing orders**, all through **one single API** that any channel (website, WhatsApp, Telegram, mobile app...) can plug into without any changes to the agent itself.

Built as a portfolio project demonstrating production-style RAG + database tool use + LLM function calling, alongside [RAG1](#related-project) (a clinical RAG decision-support assistant).

---

## Why this is different from a typical RAG chatbot

Most "AI chatbot" projects only do one thing: retrieve text from documents and answer questions about it. This project goes further, combining **three separate capabilities behind one conversational interface**:

| Capability | How | Example question |
|---|---|---|
| Answer from structured data | Direct PostgreSQL queries | *"What's the price of the LG Pixel13 headphones?"* |
| Answer from policy documents | Hybrid RAG (BM25 + semantic + reranking) | *"How long do I have to return something?"* |
| Take real actions | LLM function calling, writes to the database | *"Place an order for 2 of product X."* |

The agent decides which of these to use — or combine — for any given message, without the developer hard-coding intent-matching rules.

---

## Channel-agnostic by design

The entire agent lives behind **one HTTP endpoint** (`POST /chat`). A website widget, a WhatsApp integration, a Telegram bot, or a mobile app all talk to the exact same endpoint the exact same way — send a message and a session ID, get a reply back. None of them need to know anything about Postgres, ChromaDB, or how the LLM decides which tool to call.

```
Website widget ─┐
WhatsApp (future)├──►  POST /chat  ──►  Agent Core  ──┬──► PostgreSQL (products, orders)
Telegram (future)┘      {message,                     └──► ChromaDB (policies, via RAG)
                          session_id}
```

This project ships with a working website widget (see [Frontend](#frontend)) as a live proof of the design. Additional channels (WhatsApp, Telegram, etc.) can be added later as thin adapters that simply forward messages to `/chat` — **no changes to the agent itself required**. This is a natural upsell/extension point for a freelance client: *"want this on WhatsApp too? That's a small additional integration, not a rebuild."*

---

## Architecture

```
                 ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
                 │  Website    │  │  WhatsApp   │  │  Telegram    │   (channels)
                 │  (built)    │  │  (future)   │  │  (future)    │
                 └──────┬──────┘  └──────┬──────┘  └──────┬───────┘
                        └────────────────┼────────────────┘
                                         ▼
                          FastAPI  POST /chat  (single entry point)
                                         ▼
                         Agent Core (Gemini function calling)
                       ┌─────────────────┴─────────────────┐
                       ▼                                   ▼
              DB Tools (structured data)           RAG Tool (unstructured data)
        get_product_info / check_stock /          search_policy() — hybrid
        place_order / get_order_status             BM25 + semantic + reranking
                       │                                   │
                       ▼                                   ▼
                 PostgreSQL                          ChromaDB
           (products, customers,                 (shipping / return /
              order_items)                     warranty / FAQ — bilingual
                                                     Arabic + English)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend framework | Python, FastAPI |
| Structured database | PostgreSQL (Docker) |
| ORM | SQLAlchemy |
| Vector database | ChromaDB |
| Embeddings | Gemini `gemini-embedding-001` |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` (sentence-transformers) |
| Keyword search | BM25 (`rank_bm25`) |
| Agent LLM | Gemini, function calling (`gemini-flash-latest`) |
| Frontend | Plain HTML/CSS/JavaScript (no framework — see [Frontend](#frontend)) |

---

## Key features

- **Hybrid retrieval RAG** — combines keyword search (BM25) and semantic search (embeddings), then reranks with a cross-encoder for accuracy — the same architecture used in the author's clinical RAG project, applied here to a completely different industry.
- **Bilingual policy support** — shipping, return, warranty, and FAQ content is available in both Arabic and English, and the agent responds in whichever language the customer used.
- **Real database actions** — the agent can place actual orders (writing to PostgreSQL, decrementing stock) and check real order status, not just answer questions.
- **Session-based conversation memory** — the agent remembers earlier turns in the same conversation (e.g. "is *it* in stock?" correctly resolves to a product mentioned two messages earlier).
- **Scope-safe by design** — a dedicated system prompt keeps the agent focused on store-related topics only, and a relevance-score threshold on retrieval results prevents the agent from inventing answers when nothing relevant was actually found.
- **Resilient to real-world API flakiness** — automatic retry-with-backoff for transient Gemini API errors (server overload, rate limits).

---

## Project structure

```
ecommerce-ai-agent/
├── app/
│   ├── main.py                # FastAPI app — /chat, /chat/reset endpoints
│   ├── agent/
│   │   ├── core.py             # Function-calling loop + session memory + retry logic
│   │   ├── tools.py            # Tool schemas + dispatch (bridges LLM ↔ DB/RAG functions)
│   │   ├── prompts.py          # System prompt + safety/scope guardrails
│   │   └── memory.py           # Session-based conversation history
│   ├── db/
│   │   ├── database.py         # PostgreSQL connection (SQLAlchemy)
│   │   ├── models.py           # ORM models (Product, Customer, OrderItem)
│   │   └── queries.py          # get_product_info, check_stock, place_order, get_order_status
│   └── rag/
│       ├── vectorstore.py      # ChromaDB client/collection setup
│       ├── ingest.py           # Chunk + embed + store policy documents
│       └── retriever.py        # Hybrid search (BM25 + semantic + reranking)
├── data/
│   ├── raw/                    # Source CSVs (products, users, purchases)
│   └── policies/               # Bilingual policy documents (shipping/return/warranty/FAQ)
├── scripts/
│   └── build_database.py       # Builds and seeds the PostgreSQL database
├── frontend/
│   └── chat_widget/            # Working browser-based demo client
│       ├── index.html
│       └── chat.js
├── docker-compose.yml           # PostgreSQL service
├── requirements.txt
└── .env                         # DATABASE_URL, GEMINI_API_KEY (not committed)
```

---

## Setup & running locally

### Prerequisites
- Python 3.14+
- Docker Desktop
- A Gemini API key ([ai.google.dev](https://ai.google.dev))

### Steps

```bash
# 1. Start PostgreSQL
docker compose up -d

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# create a .env file with:
#   DATABASE_URL=postgresql://ecommerce_user:ecommerce_pass@localhost:5433/ecommerce_db
#   GEMINI_API_KEY=your_key_here

# 5. Build the database (source CSVs from Kaggle — see Data Sources below)
python scripts/build_database.py

# 6. Ingest the policy documents into ChromaDB
python -m app.rag.ingest

# 7. Start the API server
uvicorn app.main:app --reload
```

### Try it

**Via curl:**
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is your return policy?", "session_id": "demo-1"}'
```

**Via the browser widget:**
```bash
open frontend/chat_widget/index.html
```

---

## Data sources

- **Structured data:** "E-Commerce Product Intelligence Dataset" (Kaggle, MIT license) — synthetic products, users, and purchases data.
- **Policy documents:** hand-written by the author, in both Arabic and English, grounded in the dataset's real product categories.

---

## API reference

### `POST /chat`
```json
// Request
{ "message": "What's your return policy?", "session_id": "any-string-you-choose" }

// Response
{ "reply": "According to our Return Policy...", "session_id": "any-string-you-choose" }
```

### `POST /chat/reset?session_id=...`
Clears a session's conversation memory.

### `GET /`
Health check.

---

## Frontend

A minimal but functional chat widget is included (`frontend/chat_widget/`) to demonstrate the API working from a real browser client, complete with conversation memory and a reset button. See `FRONTEND_IMPROVEMENTS.md` for a plan to polish this further.

---

## Possible extensions

- **Additional channels** — WhatsApp (via Twilio/WhatsApp Cloud API) or Telegram adapters, each a thin wrapper calling the same `/chat` endpoint.
- **Product review search** — a dedicated `search_product_reviews()` tool (deliberately kept separate from the policy RAG to avoid degrading retrieval quality).
- **Persistent memory** — swap the in-memory session store for Redis or a database table for multi-process/production deployments.
- **Streaming responses** — word-by-word display in the frontend for a more "live typing" feel.

---

## Related project

This project deliberately reuses the hybrid retrieval architecture (BM25 + semantic search + cross-encoder reranking) from an earlier project: a **clinical RAG decision-support assistant** built on NICE guidelines, using FastAPI, Streamlit, and ChromaDB. Applying the same retrieval design to e-commerce demonstrates that the underlying approach generalizes across industries — from healthcare guidance to customer support.

---

## License

This is a portfolio/demonstration project. The underlying dataset is used under its MIT license from Kaggle.
