"""
tests/test_agent.py

Test suite covering the project's key components. Split into two
groups, marked accordingly:

1. FAST / OFFLINE-SAFE tests — hit the local Postgres DB directly
   (via db/queries.py) or just check object structure (tools.py
   schemas). These don't call the Gemini API, so they're safe to run
   repeatedly without touching the daily free-tier quota.

2. INTEGRATION tests (marked @pytest.mark.integration) — call the
   real Gemini API (embeddings for RAG search, or the full agent loop).
   These DO consume API quota, so they're skipped by default. Run them
   deliberately with:
       pytest -m integration

Run everything except integration tests (the safe default):
    pytest

Prerequisites for ANY of these tests to pass:
    - docker compose up -d (Postgres running)
    - scripts/build_database.py already run at least once
    - python -m app.rag.ingest already run at least once (for integration tests)
"""

import pytest

from app.db.queries import get_product_info, check_stock, get_order_status
from app.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS


# ── Fast / offline-safe tests ────────────────────────────────────────

class TestDatabaseQueries:
    """These hit the live local Postgres DB but never call Gemini."""

    def test_get_product_info_by_name_returns_list(self):
        results = get_product_info("Wireless")
        assert isinstance(results, list)
        assert len(results) > 0
        for product in results:
            assert "product_id" in product
            assert "name" in product
            assert "price" in product
            assert "stock_quantity" in product

    def test_get_product_info_by_exact_id_returns_single_dict(self):
        matches = get_product_info("Wireless")
        assert len(matches) > 0
        product_id = matches[0]["product_id"]

        result = get_product_info(product_id)
        assert isinstance(result, dict)
        assert result["product_id"] == product_id

    def test_get_product_info_unknown_name_returns_empty_list(self):
        results = get_product_info("zzznonexistentproductxyz")
        assert results == []

    def test_check_stock_returns_expected_shape(self):
        matches = get_product_info("Wireless")
        product_id = matches[0]["product_id"]

        result = check_stock(product_id)
        assert result is not None
        assert "in_stock" in result
        assert "stock_quantity" in result
        assert isinstance(result["in_stock"], bool)

    def test_check_stock_unknown_product_returns_none(self):
        result = check_stock("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_get_order_status_unknown_order_returns_none(self):
        result = get_order_status("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestAgentToolSchemas:
    """
    Pure structure checks — confirm the 5 tools are defined and the
    dispatch dict actually maps to real, callable functions. No API
    calls, no database calls beyond what get_product_info needs.
    """

    def test_five_tools_defined(self):
        assert len(TOOL_SCHEMAS) == 5

    def test_expected_tool_names_present(self):
        names = {t.name for t in TOOL_SCHEMAS}
        assert names == {
            "get_product_info",
            "check_stock",
            "place_order",
            "get_order_status",
            "search_policy",
        }

    def test_every_schema_has_a_dispatch_function(self):
        for tool in TOOL_SCHEMAS:
            assert tool.name in TOOL_FUNCTIONS
            assert callable(TOOL_FUNCTIONS[tool.name])

    def test_dispatch_actually_calls_through_correctly(self):
        result = TOOL_FUNCTIONS["get_product_info"]("Wireless")
        assert isinstance(result, list)
        assert len(result) > 0


# ── Integration tests (consume Gemini API quota — run deliberately) ──

@pytest.mark.integration
class TestPolicyRetrieval:
    """Calls the real Gemini embedding API — costs quota, skipped by default."""

    def test_search_policy_returns_relevant_results(self):
        from app.rag.retriever import search_policy

        results = search_policy("How long do I have to return a product?")
        assert isinstance(results, list)
        assert len(results) > 0
        assert "return_policy" in results[0]["source"]

    def test_search_policy_arabic_query_works(self):
        from app.rag.retriever import search_policy

        results = search_policy("كام مدة الضمان على الإلكترونيات؟")
        assert isinstance(results, list)
        assert len(results) > 0
        assert results[0]["language"] == "ar"


@pytest.mark.integration
class TestAgentEndToEnd:
    """Calls the real Gemini function-calling API — costs quota, skipped by default."""

    def test_policy_question_produces_an_answer(self):
        from app.agent.core import run_agent

        reply = run_agent("What's your return policy?", session_id="pytest-policy")
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_conversation_memory_resolves_pronoun(self):
        from app.agent.core import run_agent

        session = "pytest-memory"
        first_reply = run_agent(
            "What's the price of the LG Pixel13 Wireless Headphones?", session_id=session
        )
        assert "127.25" in first_reply or "$127" in first_reply

        second_reply = run_agent("Is it in stock?", session_id=session)
        assert "which product" not in second_reply.lower()
