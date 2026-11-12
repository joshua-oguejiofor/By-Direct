from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrderStatus

from .base import Base, UpdateTimestampMixin


class Order(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    order_number: Mapped[str] = mapped_column(sa.String(50), unique=True, nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(sa.Enum(OrderStatus, values_callable=lambda enum_class: [item.value for item in enum_class]), nullable=False, default=OrderStatus.PENDING)
    total_amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    shipping_amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    shipping_address: Mapped[dict[str, Any]] = mapped_column(sa.JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True, default=None)
    contact_number: Mapped[str] = mapped_column(sa.String(30), nullable=True, default=None)
    expiration_cutoff: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="orders")  # type: ignore # noqa: F821
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payment: Mapped["Payment"] = relationship(back_populates="order", uselist=False) # type: ignore  # noqa: F821
    # Relationship to audit logs (sorted chronologically)
    status_audits: Mapped[list["OrderStatusAudit"]] = relationship(back_populates="order", order_by="OrderStatusAudit.created_at.asc()", cascade="all, delete-orphan")


class OrderItem(Base):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    product_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
   

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")  # type: ignore  # noqa: F821



class OrderStatusAudit(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    
    # Track the transition state
    old_status: Mapped[OrderStatus] = mapped_column(sa.Enum(OrderStatus, native_enum=False), nullable=False)
    new_status: Mapped[OrderStatus] = mapped_column(sa.Enum(OrderStatus, native_enum=False), nullable=False)
    
    # Audit details: Who, When, Why
    changed_by_user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    
    # Composite index for efficient historical timeline lookups
    __table_args__ = (
        sa.Index("ix_order_status_audits_order_created", "order_id", "created_at"),
    )

   
    # Relationships
    order: Mapped["Order"] = relationship(back_populates="status_audits")


