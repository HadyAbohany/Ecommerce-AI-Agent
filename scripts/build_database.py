"""
build_database.py

Builds the PostgreSQL database for the e-commerce AI Agent project,
using the "E-Commerce Product Intelligence Dataset" from Kaggle.

Uses: products.csv, users.csv, purchases.csv
(reviews.csv is loaded separately later, once we add the
 search_product_reviews() tool — not needed for the core agent yet)

IMPORTANT: purchases.csv is really "order line items" — one order_id
can appear on multiple rows (one row per product in that order).
So the unique primary key is purchase_id (the line item), NOT order_id.
The table is named "order_items" to reflect this correctly.

PREREQUISITES:
- Docker container running (docker compose up -d)
- .env file with DATABASE_URL set
- CSVs placed in data/raw/

USAGE (run from the project root):
    python scripts/build_database.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found. Check your .env file.")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# ── COLUMN MAPS ──────────────────────────────────────────────────────

# products.csv columns:
# product_id,product_name,product_description,category,subcategory,
# brand,price,rating_avg,review_count,stock_quantity,date_added
PRODUCT_COLS = {
    "product_id": "product_id",
    "name": "product_name",
    "category": "category",
    "subcategory": "subcategory",
    "brand": "brand",
    "description": "product_description",
    "price": "price",
    "stock_quantity": "stock_quantity",
    "rating": "rating_avg",
}

# users.csv columns:
# user_id,age,gender,country,city,signup_date,income_level,
# preferred_category,loyalty_tier
USER_COLS = {
    "user_id": "user_id",
    "age": "age",
    "country": "country",
    "city": "city",
    "income_level": "income_level",
    "loyalty_tier": "loyalty_tier",
}

# purchases.csv columns:
# purchase_id,order_id,user_id,product_id,session_id,interaction_id,
# quantity,unit_price,total_amount,order_date
#
# purchase_id = unique line item ID (PRIMARY KEY)
# order_id    = groups multiple line items into one order (NOT unique)
PURCHASE_COLS = {
    "purchase_id": "purchase_id",
    "order_id": "order_id",
    "user_id": "user_id",
    "product_id": "product_id",
    "quantity": "quantity",
    "unit_price": "unit_price",
    "total_amount": "total_amount",
    "order_date": "order_date",
}

# ── SCHEMA ────────────────────────────────────────────────────────────

SCHEMA = """
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS reviews CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE products (
    product_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT,
    subcategory     TEXT,
    brand           TEXT,
    description     TEXT,
    price           NUMERIC,
    stock_quantity  INTEGER,
    rating          NUMERIC
);

CREATE TABLE customers (
    user_id         TEXT PRIMARY KEY,
    name            TEXT,
    age             INTEGER,
    country         TEXT,
    city            TEXT,
    income_level    TEXT,
    loyalty_tier    TEXT
);

-- One row per product within an order (a "line item").
-- order_id groups rows that belong to the same order/checkout.
CREATE TABLE order_items (
    purchase_id     TEXT PRIMARY KEY,
    order_id        TEXT NOT NULL,
    user_id         TEXT REFERENCES customers(user_id),
    product_id      TEXT REFERENCES products(product_id),
    quantity        INTEGER,
    unit_price      NUMERIC,
    total_amount    NUMERIC,
    order_date      TIMESTAMP,
    status          TEXT DEFAULT 'delivered'
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_user_id ON order_items(user_id);
"""


def safe_read_csv(filename: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Could not find {filename} in {DATA_DIR}. "
            f"Download it from Kaggle and place it in data/raw/."
        )
    return pd.read_csv(path)


def map_columns(df: pd.DataFrame, col_map: dict, table_name: str) -> pd.DataFrame:
    rename_dict = {}
    missing = []
    for our_col, csv_col in col_map.items():
        if csv_col in df.columns:
            rename_dict[csv_col] = our_col
        else:
            missing.append((our_col, csv_col))

    if missing:
        print(f"[{table_name}] WARNING: expected columns not found in CSV:")
        for our_col, csv_col in missing:
            print(f"   - expected '{csv_col}' for '{our_col}' -> filled with defaults")

    df = df.rename(columns=rename_dict)
    for our_col in col_map.keys():
        if our_col not in df.columns:
            df[our_col] = None

    return df[list(col_map.keys())]


def build_database():
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        conn.execute(text(SCHEMA))
    print("Schema created in PostgreSQL.")

    # ── Products ──
    products_df = safe_read_csv("products.csv")
    products_df = map_columns(products_df, PRODUCT_COLS, "products")
    products_df.to_sql("products", engine, if_exists="append", index=False)
    print(f"Inserted {len(products_df)} products.")

    # ── Customers ──
    users_df = safe_read_csv("users.csv")
    users_df = map_columns(users_df, USER_COLS, "customers")
    users_df["name"] = "Customer " + users_df["user_id"].astype(str)
    users_df = users_df[["user_id", "name", "age", "country", "city", "income_level", "loyalty_tier"]]
    users_df.to_sql("customers", engine, if_exists="append", index=False)
    print(f"Inserted {len(users_df)} customers.")

    # ── Order items (from purchases.csv) ──
    purchases_df = safe_read_csv("purchases.csv")
    purchases_df = map_columns(purchases_df, PURCHASE_COLS, "order_items")
    purchases_df["status"] = "delivered"

    # Sanity check: purchase_id must be unique before inserting
    dupes = purchases_df["purchase_id"].duplicated().sum()
    if dupes > 0:
        print(f"WARNING: {dupes} duplicate purchase_id values found — dropping duplicates.")
        purchases_df = purchases_df.drop_duplicates(subset="purchase_id")

    purchases_df.to_sql("order_items", engine, if_exists="append", index=False)
    print(f"Inserted {len(purchases_df)} order line items "
          f"({purchases_df['order_id'].nunique()} unique orders).")

    # ── Verify ──
    print("\n--- Verification ---")
    with engine.connect() as conn:
        for table in ["products", "customers", "order_items"]:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"{table}: {count} rows")

    print("\nDone. PostgreSQL database is ready.")


if __name__ == "__main__":
    build_database()