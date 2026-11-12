from datetime import datetime

from pydantic import Field

from app.shared.schema import LoweredStripedSchema, SharedResponseSchema


class ReviewCreate(LoweredStripedSchema):
    product_id: int = Field(ge=1)
    rating: int = Field(ge=1, le=5)
    comment: str | None = None



class _ReviewResponse(LoweredStripedSchema):
    id: int
    user_id: int
    product_id: int
    rating: int
    comment: str | None
    is_approved: bool
    is_verified_purchase: bool
    created_at: datetime

class ReviewlistResponse(SharedResponseSchema):
    reviews: list[_ReviewResponse]
    count: int
    page: int
    page_size: int
    total_pages: int
    
    
