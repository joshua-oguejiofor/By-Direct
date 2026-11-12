from datetime import datetime
from decimal import Decimal

from app.shared.schema import SharedResponseSchema


class PaymentResponse(SharedResponseSchema):
    id: int
    order_id: int
    amount: Decimal
    currency: str
    status: str
    provider: str
    provider_reference: str
    created_at: datetime


class PaymentResponseList(SharedResponseSchema):
    payments: list[PaymentResponse]
    page: int
    page_size: int
    count: int
    total_pages: int