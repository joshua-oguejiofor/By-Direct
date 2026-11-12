from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Wishlist(Base, TimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="wishlist")  # type: ignore # noqa: F821
    items: Mapped[list["WishlistItem"]] = relationship(back_populates="wishlist", cascade="all, delete-orphan")


class WishlistItem(Base):
    __table_args__ = (
        sa.UniqueConstraint("wishlist_id", "product_id", name="uq_wishlist_product"),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    wishlist_id: Mapped[int] = mapped_column(sa.ForeignKey("wishlists.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())

    # Relationships
    wishlist: Mapped["Wishlist"] = relationship(back_populates="items")  # type: ignore
    product: Mapped["Product"] = relationship(back_populates="wishlist_items")  # type: ignore # noqa: F821