from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UpdateTimestampMixin


class Product(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(sa.String(300), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True, default=None)
    price: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    discount_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 2), nullable=True, default=None)
    stock_quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    category_id: Mapped[int] = mapped_column(sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, default=None)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    is_featured: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    brand: Mapped[str | None] = mapped_column(sa.String(100), nullable=False, default=None)
    average_rating: Mapped[float] = mapped_column(sa.Float, nullable=True, default=0.0)
    total_reviews: Mapped[int] = mapped_column(sa.Integer, nullable=True, default=0)
    

    # Relationships
    category: Mapped["Category"] = relationship(back_populates="products")  # type: ignore # noqa: F821
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="product", cascade="all, delete-orphan")  # type: ignore # noqa: F821
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")  # type: ignore # noqa: F821
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="product", cascade="all, delete-orphan")  # type: ignore # noqa: F821
    wishlist_items: Mapped[list["WishlistItem"]] = relationship(back_populates="product", cascade="all, delete-orphan")  # type: ignore # noqa: F821


class ProductImage(Base, TimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    public_id: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    alt_text: Mapped[str] = mapped_column(sa.String(200), nullable=True, default=None)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    
    # Relationships
    product: Mapped["Product"] = relationship(back_populates="images")
