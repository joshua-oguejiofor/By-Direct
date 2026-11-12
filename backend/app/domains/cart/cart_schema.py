from decimal import Decimal

from pydantic import Field

from app.shared.schema import LoweredStripedSchema, SharedResponseSchema, StripedSchema


class CartItemAdd(StripedSchema):
    product_id: int = Field(..., ge=1)
    quantity: int = Field(..., ge=1)



class CartItemResponse(LoweredStripedSchema):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    in_stock: bool



class CartResponse(SharedResponseSchema):
    id: int | None
    items: list[CartItemResponse]
    total_items: int
    total_amount: Decimal

