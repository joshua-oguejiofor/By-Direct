import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(sa.String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=True, default=None)
    parent_id: Mapped[int] = mapped_column(sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, default=None)
    
    # Self-referential relationship (Parent -> Children)
    parent: Mapped["Category"] = relationship(
        remote_side=[id], 
        back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(
        "Category", 
        back_populates="parent"
    )

    # One-to-Many relationship with Product
    products: Mapped[list["Product"]] = relationship(back_populates="category")  # type: ignore # noqa: F821