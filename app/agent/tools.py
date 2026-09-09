"""
app/agent/tools.py

Wraps the already-tested functions from db/queries.py and rag/retriever.py
into Gemini function-calling tool definitions, plus a dispatch mapping so
agent/core.py (Step 6) can actually execute whatever the LLM decides to call.

Nothing new is implemented here — this is pure packaging of Step 3 and
Step 4's work into the shape Gemini's function calling expects.
"""

from google.genai import types

from app.db.queries import get_product_info, check_stock, place_order, get_order_status
from app.rag.retriever import search_policy


# ── Tool schemas (what the LLM sees, to decide which tool to call) ──

get_product_info_decl = types.FunctionDeclaration(
    name="get_product_info",
    description=(
        "Look up details about a specific product — price, description, category, "
        "brand, and rating. Use this when the customer asks about a product's price, "
        "what it is, or general details. Search by product name (partial match is fine) "
        "or by an exact product ID if one is already known from earlier in the conversation. "
        "For stock/availability questions specifically, use check_stock instead."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "product_name_or_id": types.Schema(
                type=types.Type.STRING,
                description="The product name (or partial name) to search for, or an exact product UUID.",
            ),
        },
        required=["product_name_or_id"],
    ),
)

check_stock_decl = types.FunctionDeclaration(
    name="check_stock",
    description=(
        "Check whether a specific product is currently in stock and how many units "
        "are available. Use this specifically when the customer asks if an item is "
        "available, in stock, or how many are left — NOT for general product details "
        "like price or description (use get_product_info for that). Requires an exact "
        "product_id — if you only have a product name, call get_product_info first to "
        "resolve it to an ID."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "product_id": types.Schema(
                type=types.Type.STRING,
                description="The exact product UUID to check stock for.",
            ),
        },
        required=["product_id"],
    ),
)

place_order_decl = types.FunctionDeclaration(
    name="place_order",
    description=(
        "Place a new order for a customer. Only call this once you have all three "
        "required pieces of information confirmed with the customer: their user_id, "
        "the exact product_id they want, and the quantity. Do not guess or invent any "
        "of these values — if any are missing, ask the customer for them first instead "
        "of calling this tool. This tool checks stock availability itself and will "
        "return an error if there isn't enough stock."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "user_id": types.Schema(
                type=types.Type.STRING,
                description="The exact customer UUID placing the order.",
            ),
            "product_id": types.Schema(
                type=types.Type.STRING,
                description="The exact product UUID being ordered.",
            ),
            "quantity": types.Schema(
                type=types.Type.INTEGER,
                description="How many units of this product to order. Must be a positive integer.",
            ),
        },
        required=["user_id", "product_id", "quantity"],
    ),
)

get_order_status_decl = types.FunctionDeclaration(
    name="get_order_status",
    description=(
        "Look up the status and details of an existing order — whether it's pending, "
        "delivered, etc., along with the items and total amount. Use this when the "
        "customer asks about the status of an order they already placed. Requires the "
        "exact order_id; if the customer doesn't have it, you cannot look up their order "
        "by name or product alone."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "order_id": types.Schema(
                type=types.Type.STRING,
                description="The exact order UUID to look up.",
            ),
        },
        required=["order_id"],
    ),
)

search_policy_decl = types.FunctionDeclaration(
    name="search_policy",
    description=(
        "Search the store's shipping, return, warranty, and FAQ policies to answer "
        "general store-policy questions — e.g. 'how long do I have to return something', "
        "'do you ship internationally', 'what's the warranty on electronics', 'what payment "
        "methods do you accept'. Use this ONLY for policy/FAQ questions, NOT for questions "
        "about a specific product's details (use get_product_info) or a specific order's "
        "status (use get_order_status). Works with questions in either Arabic or English."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "question": types.Schema(
                type=types.Type.STRING,
                description="The customer's policy-related question, in their own words and language.",
            ),
        },
        required=["question"],
    ),
)


# The full set of tool declarations, ready to pass into a Gemini call as:
#   types.Tool(function_declarations=TOOL_SCHEMAS)
TOOL_SCHEMAS = [
    get_product_info_decl,
    check_stock_decl,
    place_order_decl,
    get_order_status_decl,
    search_policy_decl,
]


# ── Dispatch mapping (what agent/core.py actually calls) ────────────

TOOL_FUNCTIONS = {
    "get_product_info": get_product_info,
    "check_stock": check_stock,
    "place_order": place_order,
    "get_order_status": get_order_status,
    "search_policy": search_policy,
}
