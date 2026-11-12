from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UpdateTimestampMixin


class Cart(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="cart")  # type: ignore # noqa: F821
    
    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base, TimestampMixin):
    
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    cart_id: Mapped[int] = mapped_column(sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    

    cart: Mapped["Cart"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="cart_items")  # type: ignore # noqa: F821