from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PaymentProvider, PaymentStatus

from .base import Base, UpdateTimestampMixin


class Payment(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(10), nullable=False, default="ngn")
    status: Mapped[PaymentStatus] = mapped_column(sa.Enum(PaymentStatus, values_callable=lambda enum_class: [item.value for item in enum_class]), nullable=False, default=PaymentStatus.PENDING)
    provider: Mapped[PaymentProvider] = mapped_column(sa.Enum(PaymentProvider, values_callable=lambda enum_class: [item.value for item in enum_class]), nullable=False)
    provider_reference: Mapped[str] = mapped_column(sa.String(200), nullable=False, default=None)
    

    # One-to-One Relationship with Order
    order: Mapped["Order"] = relationship(back_populates="payment")  # type: ignore # noqa: F821