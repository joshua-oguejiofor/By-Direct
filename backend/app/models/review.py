import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UpdateTimestampMixin


class Review(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True, default=None)
    is_verified_purchase: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_approved: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    
    __table_args__ = (sa.UniqueConstraint("user_id", "product_id", name="uq_review_user_product"),)
 

    # Relationships
    user: Mapped["User"] = relationship(back_populates="reviews")  # type: ignore # noqa: F821
    product: Mapped["Product"] = relationship(back_populates="reviews")  # type: ignore # noqa: F821