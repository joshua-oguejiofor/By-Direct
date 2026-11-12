from pydantic import Field

from app.shared.schema import LoweredStripedSchema, SharedResponseSchema


class AddCategory(LoweredStripedSchema):
    name: str
    description: str | None = None
    parent_id: int | None = Field(None, ge=1)


class CategoryResponse(SharedResponseSchema):
    id: int
    name: str
    slug: str
    description: str | None
