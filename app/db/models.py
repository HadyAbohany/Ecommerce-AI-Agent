"""
ORM models mirroring the live schema built by scripts/build_database.py.

IMPORTANT: product_id, user_id, purchase_id, and order_id are all UUID
strings in the source dataset (e.g. "af3bccbc-763f-4162-a178-bf20bfaeccba"),
NOT integers. Using Integer here would break every query against the
real data — keep these as String/TEXT to match the actual Postgres schema.
"""
from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.database import Base


class Product(Base):
    __tablename__ = "products"

    product_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String)
    subcategory = Column(String)
    brand = Column(String)
    description = Column(String)
    price = Column(Numeric(10, 2), nullable=False)
    stock_quantity = Column(Integer, nullable=False, default=0)
    rating = Column(Numeric(3, 2))

    order_items = relationship("OrderItem", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    user_id = Column(String, primary_key=True)
    name = Column(String)  # generated placeholder, per source dataset
    age = Column(Integer)
    country = Column(String)
    city = Column(String)
    income_level = Column(String)
    loyalty_tier = Column(String)

    order_items = relationship("OrderItem", back_populates="customer")


class OrderItem(Base):
    __tablename__ = "order_items"

    purchase_id = Column(String, primary_key=True)  # true unique key (UUID, per-line-item)
    order_id = Column(String, index=True, nullable=False)  # NOT unique — groups line items, also UUID
    user_id = Column(String, ForeignKey("customers.user_id"), index=True, nullable=False)
    product_id = Column(String, ForeignKey("products.product_id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    order_date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="delivered")

    product = relationship("Product", back_populates="order_items")
    customer = relationship("Customer", back_populates="order_items")