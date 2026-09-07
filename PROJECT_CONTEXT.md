# Project Context & Handoff Doc — E-commerce AI Agent

> **Purpose of this file:** This is a living log of the project — decisions made, current state, and what's next. If you (or any AI assistant) are picking this up fresh, read this file first before touching any code.

---

## 1. Project Vision

Not a simple RAG chatbot — a full **AI Agent** for e-commerce that:
1. **Answers questions** from two types of data:
   - Structured data (products, stock, orders) → via direct **database queries**
   - Unstructured data (policies, FAQ) → via **RAG** (retrieval-augmented generation)
2. **Takes actions** (place orders, check order status) via **LLM function calling** — not just Q&A
3. Is exposed through **one single API** (`/chat`) that any channel (website, WhatsApp, Telegram) can plug into, without rebuilding agent logic per channel

This is portfolio project #2, meant to broaden the developer's portfolio beyond the existing clinical RAG project ([[rag1]] — a NICE-guidelines healthcare RAG assistant with hybrid retrieval: BM25 + semantic + cross-encoder reranking, built with FastAPI/Streamlit/ChromaDB/Gemini).

---

## 2. Tech Stack (decided)

| Layer | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI | Matches existing skill set |
| Structured data DB | **PostgreSQL**, run via Docker | More "production-looking" for portfolio than SQLite |
| Vector DB (policies) | ChromaDB | Reusing hybrid retrieval logic from RAG1 project |
| LLM | Gemini API (function calling) | Same as RAG1; OpenAI is a fallback option |
| Agent orchestration | Lightweight custom function-calling loop (or LangChain) | Custom loop shows deeper understanding for portfolio purposes |
| Local dev | macOS, Docker Desktop, Python 3.14, `.venv` | — |

**Known local environment quirk:** Postgres container had to be remapped from host port 5432 → **5433**, because another local PostgreSQL instance was already bound to 5432 on this Mac, causing `role does not exist` errors that were actually a "wrong server" issue, not a real auth problem. `DATABASE_URL` in `.env` reflects port 5433.

---

## 3. Data Source (decided)

Kaggle dataset: **"E-Commerce Product Intelligence Dataset"** (synthetic, MIT license).
Files used: `products.csv`, `users.csv`, `purchases.csv` (all in `data/raw/`).
File **not** used yet: `reviews.csv` — deliberately deferred (see Design Decisions below).
Files **not used** at all: `sessions.csv`, `interactions.csv` (built for recommendation systems / GNNs — out of scope for this agent project).

### Actual CSV column names (verified — use these, not guesses)
- `products.csv`: `product_id, product_name, product_description, category, subcategory, brand, price, rating_avg, review_count, stock_quantity, date_added`
- `users.csv`: `user_id, age, gender, country, city, signup_date, income_level, preferred_category, loyalty_tier` (no name/email — names are generated as placeholders)
- `purchases.csv`: `purchase_id, order_id, user_id, product_id, session_id, interaction_id, quantity, unit_price, total_amount, order_date` (no order_status column — defaulted to `'delivered'`)

---

## 4. Database Schema (current, live in Postgres)

**Important gotcha already solved:** In `purchases.csv`, `order_id` is **not unique** — one order can span multiple rows (one row per product in that order, i.e. line items). The true unique key is `purchase_id`. The table is therefore named `order_items`, not `orders`.

```sql
products (
    product_id PK, name, category, subcategory, brand,
    description, price, stock_quantity, rating
)

customers (
    user_id PK, name (generated placeholder), age, country, city,
    income_level, loyalty_tier
)

order_items (
    purchase_id PK,           -- the real unique line-item id
    order_id (not unique),    -- groups line items into one order
    user_id FK -> customers,
    product_id FK -> products,
    quantity, unit_price, total_amount, order_date,
    status DEFAULT 'delivered'
)
-- indexes on order_id and user_id for fast lookups
```

Row counts after successful build: 1000 products, 10000 customers, 1737 order line items (1440 unique orders).

---

## 5. Project Folder Structure (agreed, final)

```
ecommerce-ai-agent/
│
├── app/
│   ├── main.py                  # FastAPI entrypoint — /chat endpoint
│   ├── agent/
│   │   ├── core.py               # agent loop: LLM decides which tool to call
│   │   ├── tools.py              # tool/function definitions
│   │   └── prompts.py            # system prompt(s)
│   ├── db/
│   │   ├── database.py           # DB connection (Postgres via SQLAlchemy)
│   │   ├── models.py             # table schemas
│   │   └── queries.py            # get_product(), check_stock(), place_order(), get_order_status()
│   ├── rag/
│   │   ├── ingest.py             # loads policy docs into ChromaDB
│   │   ├── retriever.py          # hybrid search (reused from RAG1)
│   │   └── vectorstore.py        # ChromaDB client setup
│   └── channels/                 # real channel adapters only (WhatsApp, Telegram — later)
│       └── __init__.py
│
├── data/
│   ├── raw/                      # Kaggle CSVs live here
│   └── policies/                 # shipping/return policy docs, FAQ (to be created)
│
├── scripts/
│   ├── build_database.py         # ✅ DONE — builds Postgres DB from CSVs
│   └── ingest_policies.py        # not built yet
│
├── frontend/
│   └── chat_widget/               # simple HTML/JS chat box (talks to /chat directly — not a "channel adapter")
│       ├── index.html
│       └── chat.js
│
├── tests/
│   └── test_agent.py
│
├── .env                          # DATABASE_URL (gitignored)
├── .gitignore                    # .env, *.db, __pycache__, chroma_db/
├── requirements.txt
├── docker-compose.yml            # ✅ DONE — Postgres service, port 5433:5432
└── README.md
```

**Design decisions behind this structure:**
- `agent/` never talks to the DB or ChromaDB directly — it only calls `tools.py`, which wraps `db/queries.py` and `rag/retriever.py`. Keeps "brain" separate from "hands."
- `channels/` is reserved for real protocol adapters (WhatsApp/Telegram API integration). The website widget is NOT a channel adapter — it just calls `/chat` directly like any HTTP client, so it lives in `frontend/`, not `app/channels/`.
- `reviews.csv` / product reviews are deliberately **not** part of the core policy RAG. Mixing review text with policy text would hurt retrieval quality (a policy question could wrongly retrieve review snippets). Reviews will become their own tool — `search_product_reviews()` — added after the core agent works.

---

## 6. Build Order (agreed — follow this sequence)

```
1. Dataset                     ✅ DONE
2. PostgreSQL (Docker)         ✅ DONE
3. Database queries            ⬅ NEXT STEP
4. Policy RAG
5. Agent tools
6. Function calling (agent core)
7. Conversation memory
8. FastAPI /chat endpoint
9. Website chat widget
10. Tests + README + demo video
```

Do not skip ahead — each step should be testable/runnable on its own before moving to the next (e.g., test DB query functions directly in a Python shell before wiring them into the agent).

---

## 7. Current Status (update this section as you progress)

**Last completed step:** Step 2 & the data-loading part of Step 3 — `scripts/build_database.py` runs successfully end-to-end, PostgreSQL is fully populated and verified.

**Next immediate step:** Write `app/db/queries.py` — functions like:
- `get_product_info(product_name_or_id)`
- `check_stock(product_id)`
- `get_order_status(order_id)`
- `place_order(user_id, product_id, quantity)` (needs to generate new purchase_id/order_id and insert)

**Not started yet:** RAG policy ingestion (no policy documents written/collected yet — need to draft shipping policy, return policy, FAQ text files for `data/policies/`), agent core, FastAPI app, frontend, tests.

---

## 8. Environment Setup Reference (for a fresh machine or new AI session)

```bash
# 1. Start Postgres
docker compose up -d

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Build the database (only needed once, or after schema changes)
python scripts/build_database.py
```

`.env` contents (not committed to git):
```
DATABASE_URL=postgresql://ecommerce_user:ecommerce_pass@localhost:5433/ecommerce_db
```

---

## 9. Related Project

This project deliberately reuses architecture/skills from an earlier hackathon project, **RAG1** (clinical RAG decision-support assistant, NICE guidelines, FastAPI + Streamlit + ChromaDB + hybrid retrieval + Gemini). Mentioning this connection in the portfolio description is intentional — it shows the same retrieval architecture applied across two different industries (healthcare → e-commerce).

