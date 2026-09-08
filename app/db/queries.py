"""
Direct DB query functions. These are the *only* things agent/tools.py is
allowed to import from db/ — agent/core.py never touches SQLAlchemy directly.

Each function returns plain dicts/lists (JSON-serializable), not ORM objects,
so they can be dropped straight into an LLM function-calling response.

NOTE: product_id, user_id, purchase_id, order_id are all UUID strings
(not integers) in this dataset — every lookup and ID-generation below
is written accordingly.
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Product, Customer, OrderItem


def get_product_info(product_name_or_id: str, db: Session = None):
    """
    Look up a product by exact product_id (UUID string), or by fuzzy name match.
    Returns a single dict if looked up by id, or a list of dicts (top 5) if by name.
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        # UUIDs always contain hyphens and are 36 chars — a much safer check
        # than isdigit() (which would never match a UUID anyway).
        exact_match = db.query(Product).filter(Product.product_id == product_name_or_id).first()
        if exact_match:
            return _product_to_dict(exact_match)

        matches = (
            db.query(Product)
            .filter(Product.name.ilike(f"%{product_name_or_id}%"))
            .limit(5)
            .all()
        )
        return [_product_to_dict(p) for p in matches]
    finally:
        if own_session:
            db.close()


def check_stock(product_id: str, db: Session = None):
    """Returns current stock level for a product."""
    own_session = db is None
    db = db or SessionLocal()
    try:
        p = db.query(Product).filter(Product.product_id == product_id).first()
        if not p:
            return None
        return {
            "product_id": p.product_id,
            "name": p.name,
            "in_stock": p.stock_quantity > 0,
            "stock_quantity": p.stock_quantity,
        }
    finally:
        if own_session:
            db.close()


def get_order_status(order_id: str, db: Session = None):
    """
    order_id is NOT unique per-row (it groups line items), so this returns
    the shared status + all line items belonging to that order.
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
        if not items:
            return None

        return {
            "order_id": order_id,
            "status": items[0].status,  # all line items in one order share status
            "order_date": str(items[0].order_date),
            "user_id": items[0].user_id,
            "items": [
                {
                    "purchase_id": i.purchase_id,
                    "product_id": i.product_id,
                    "quantity": i.quantity,
                    "unit_price": float(i.unit_price),
                    "total_amount": float(i.total_amount),
                }
                for i in items
            ],
            "order_total": float(sum(i.total_amount for i in items)),
        }
    finally:
        if own_session:
            db.close()


def place_order(user_id: str, product_id: str, quantity: int, db: Session = None) -> dict:
    """
    Creates a new single-line-item order: validates customer + stock,
    decrements stock, inserts an order_items row, commits.
    Returns the created order info, or a dict with an 'error' key on failure.

    New purchase_id / order_id are generated as fresh UUIDs (uuid4) —
    matching the ID style already used throughout the dataset, since
    MAX(...) + 1 only works for sequential integer keys, not UUIDs.
    """
    own_session = db is None
    db = db or SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.user_id == user_id).first()
        if not customer:
            return {"error": f"user_id {user_id} not found"}

        product = db.query(Product).filter(Product.product_id == product_id).first()
        if not product:
            return {"error": f"product_id {product_id} not found"}

        if quantity <= 0:
            return {"error": "quantity must be positive"}

        if product.stock_quantity < quantity:
            return {
                "error": "insufficient stock",
                "available": product.stock_quantity,
                "requested": quantity,
            }

        new_purchase_id = str(uuid.uuid4())
        new_order_id = str(uuid.uuid4())  # one line item = one new order, for simplicity

        unit_price = product.price
        total_amount = unit_price * quantity

        new_item = OrderItem(
            purchase_id=new_purchase_id,
            order_id=new_order_id,
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            order_date=datetime.utcnow(),
            status="pending",  # newly placed order, unlike the seeded 'delivered' rows
        )

        product.stock_quantity -= quantity

        db.add(new_item)
        db.commit()
        db.refresh(new_item)

        return {
            "order_id": new_order_id,
            "purchase_id": new_purchase_id,
            "product_id": product_id,
            "product_name": product.name,
            "quantity": quantity,
            "unit_price": float(unit_price),
            "total_amount": float(total_amount),
            "status": "pending",
            "order_date": str(new_item.order_date),
        }
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        if own_session:
            db.close()


def _product_to_dict(p: Product) -> dict:
    return {
        "product_id": p.product_id,
        "name": p.name,
        "category": p.category,
        "subcategory": p.subcategory,
        "brand": p.brand,
        "description": p.description,
        "price": float(p.price),
        "stock_quantity": p.stock_quantity,
        "rating": float(p.rating) if p.rating is not None else None,
    }