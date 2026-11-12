from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from app.core.enums import OrderStatus, PaymentProvider
from app.shared.schema import LoweredStripedSchema, SharedResponseSchema, StripedSchema
from app.shared.utility import validate_phone_number


class ShippingAddress(LoweredStripedSchema):
    street: str = Field(min_length=3, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    state: str | None = None
    postal_code: str | None = None
    country: str = Field(min_length=2, max_length=2, default="ng")           # ISO-3166 alpha-2, e.g. "NG"
    
    

class CheckoutRequest(LoweredStripedSchema):
    name: str | None = Field(None, min_length=2, max_length=100)
    shipping_address: ShippingAddress
    notes: str | None = None
    payment_provider: PaymentProvider
    contact_number: str | None = Field(None)
    
    @field_validator("contact_number", mode="before")
    @classmethod
    def validate_contact_number(cls, contact_number: str): 
        return validate_phone_number(contact_number)
     



class _OrderItemResponse(SharedResponseSchema):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    
class _Orders(SharedResponseSchema):
    id : int
    user_id: int
    order_number: str
    status: str
    total_amount: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    shipping_amount: Decimal
    shipping_address: dict
    contact_number: str | None = None
    notes: str | None
    created_at: datetime
    updated_at: datetime

class OrderResponse(SharedResponseSchema):
    orders: list[_Orders]
    count: int
    page: int
    page_size: int
    total_pages: int


class _OrderPayments(StripedSchema):
    id: int
    order_id: int
    amount: Decimal
    status: str
    currency: str
    provider: str
    provider_reference: str | None
    created_at: datetime
    updated_at: datetime


class OrderWithItemsResponse(SharedResponseSchema):
    id: int
    order_number: str
    status: str
    total_amount: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    shipping_amount: Decimal
    shipping_address: dict
    contact_number: str | None = None
    items: list[_OrderItemResponse]
    payment: _OrderPayments | None = None
    created_at: datetime


class OrderStatusAuditRead(LoweredStripedSchema):
    new_status: OrderStatus
    reason: str | None = None
