from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.core.config import settings
from app.shared.schema import SharedResponseSchema, StripedSchema
from app.shared.utility import format_strings


class CreateProductImage(StripedSchema):
    url: str 
    alt_text: str | None = None
    is_primary: bool
    public_id: str = Field(..., min_length=1, max_length=500)  # returned by Cloudinary after the upload

    @model_validator(mode="after")
    def validate_cloudinary_asset(self) -> "CreateProductImage":
        # Only accept images that were uploaded to OUR Cloudinary folder.
        # This stops a client from saving any random URL, or to delete someone else's asset.
        print("url:", self.url, "public id:", self.public_id)
        if settings.ALLOW_LOCAL_IMAGES and self.url.startswith(settings.FRONTEND_URL) and self.public_id.startswith("local/"):
            return self  # saved on the developer's own computer, not in Cloudinary
        
        cloud = settings.CLOUDINARY_CLOUD_NAME
        folder = settings.CLOUDINARY_UPLOAD_FOLDER
        if cloud and not self.url.startswith(f"{settings.CLOUDINARY_URL}/{cloud}/"):
            raise ValueError("Image url must come from our Cloudinary account")
        if not self.public_id.startswith(f"{folder}/"):
            raise ValueError("Invalid public_id")
        return self



class CreateProduct(StripedSchema):
    name: str
    description: str | None = None
    price: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    discount_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    stock_quantity: int = Field(..., ge=0)
    category_id: int = Field(..., ge=1)
    brand: str = Field(..., min_length=1, max_length=100)
    is_featured: bool = False
    is_active: bool = True
    image: CreateProductImage
    
    @field_validator("name", "description", "brand", mode="before")
    @classmethod
    def validate_string(cls, value: str):
        return format_strings(value)
    
    @model_validator(mode="after")
    def validate_discount_price(self) -> "CreateProduct":
        
        # Check if discount_price is provided and greater than or equal to regular price
        if self.discount_price is not None and self.discount_price >= self.price:
            raise ValueError("Discount price must be lower than the regular price")
        return self


class UpdateProductImage(StripedSchema):
    url: str | None = None
    alt_text: str | None
    is_primary: bool | None = None


class UpdateProduct(StripedSchema):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    discount_price: Decimal | None = Field(None, ge=0)
    stock_quantity: int | None = Field(None, ge=0)
    category_id: int | None = Field(None, ge=1)
    brand: str | None = None
    is_active: bool | None = None
    is_featured: bool | None = None
    image: UpdateProductImage
    
    @field_validator("name", "description", "brand", mode="before")
    @classmethod
    def validate_string(cls, value: str):
        return format_strings(value)
    
    @model_validator(mode="after")
    def validate_discount_price(self) -> "UpdateProduct":
        
        # Check if discount_price is provided and greater than or equal to regular price
        if (
            self.discount_price is not None 
            and self.price is not None 
            and self.discount_price >= self.price
            ):
                raise ValueError("Discount price must be lower than the regular price")
        return self


class ProductImageResponse(SharedResponseSchema):
    id: int
    product_id: int
    url: str
    alt_text: str | None = None
    is_primary: bool
    public_id: str
    created_at: datetime
    

class ProductResponse(SharedResponseSchema):
    id: int
    name: str
    slug: str
    category_id: int
    description: str | None
    price: Decimal
    discount_price: Decimal | None
    stock_quantity: int
    brand: str | None
    average_rating: float
    total_reviews: int
    is_active: bool
    is_featured: bool
    images: list[ProductImageResponse]
    created_at: datetime
    updated_at: datetime


class ProductListResponse(SharedResponseSchema):
    products: list[ProductResponse] | None
    count: int
    page: int
    page_size: int
    total_pages: int
    
    
    