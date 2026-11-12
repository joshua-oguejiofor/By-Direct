
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query

from app.depends import current_user, di_injection
from app.depends.visitor import get_optional_user
from app.models import User

from . import cloudinary_image
from .product_schema import (
    CreateProduct,
    CreateProductImage,
    ProductListResponse,
    ProductResponse,
    UpdateProduct,
)
from .product_service import ProductService

router = APIRouter()

product_service_ = Annotated[ProductService, Depends(di_injection.get_product_service)]
admin_user_ = Annotated[User, Depends(current_user.get_admins)]
superadmin_user_ = Annotated[User, Depends(current_user.get_superadmin)]
current_user_ = Annotated[User | None, Depends(get_optional_user)]  # guests can browse product


@router.get("/upload-signature", status_code=200)
async def upload_signature(admin_user: admin_user_) -> dict:
    """Step 1 for the frontend: ask for a signature, then upload the file straight to Cloudinary."""
    return cloudinary_image.sign_upload()


@router.post("/", status_code=201)
async def create_product(
    data: CreateProduct,
    service: product_service_,
    admin_user: admin_user_,
) -> dict[str, str]:
    
    await service.create_product(data=data, admin_user=admin_user)
    return {"msg": f"Product {data.name} added successfully"}


@router.get("/", response_model=ProductListResponse, status_code=200)
async def get_products(
    current_user: current_user_,
    service: product_service_,
    page: int=Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)  # le=50 sets the upper bound! A query can't request more that 50 at once
    ):

    return await service.get_all_product(page=page, page_size=page_size, current_user=current_user)



@router.get("/search", response_model=ProductListResponse, status_code=200)
async def search_products(
    service: product_service_,
    current_user: current_user_,
    query: str | None = Query(None, description="Search query"),
    slug: str | None = Query(None, description="Search by product slug"),
    category_id: int | None = Query(None, description="Search be category id"),
    min_price: float | None = Query(None, description="Search by minmum product price"),
    max_price: float | None = Query(None, description="Search by maximum product price"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    
    return await service.search_products(
        current_user=current_user,
        category_id=category_id,
        slug=slug,
        query=query, 
        min_price=min_price, 
        max_price=max_price, 
        page=page, page_size=page_size
        )



@router.get("/{product_id}", response_model=ProductResponse, status_code=200)
async def get_product(
    current_user: current_user_, 
    service: product_service_,
    product_id: int = Path(..., ge=1),
    ):
    
    return await service.get_product_by_id(product_id, current_user=current_user)


@router.patch("/{product_id}", status_code=200)
async def update_product(
    data: UpdateProduct,
    admin_user: admin_user_,
    service: product_service_,
    product_id: int = Path(..., ge=1),
    
) -> dict[str, str]:
    await service.update_product(product_id=product_id, data=data, admin_user=admin_user)
    return {"msg": f"Product {product_id} updated successfully"}
    

@router.delete("/{product_id}", status_code=204)
async def delete_product(
    superadmin: superadmin_user_,
    service: product_service_,
    background_tasks: BackgroundTasks,
    product_id: int = Path(..., ge=1),
):
    return await service.delete_product(product_id=product_id, superadmin=superadmin, background_tasks=background_tasks)
    


@router.post("/{product_id}/images", status_code=201)
async def add_product_image(
    data: CreateProductImage,
    admin_user: admin_user_,
    service: product_service_,
    product_id: int = Path(..., ge=1),
) -> dict[str, str]:
    await service.add_image(product_id=product_id, data=data, admin_user=admin_user)
    return {"msg": "Image added"}


@router.delete("/{product_id}/images/{image_id}", status_code=204)
async def delete_product_image(
    admin_user: admin_user_,
    service: product_service_,
    background_tasks: BackgroundTasks,
    product_id: int = Path(..., ge=1),
    image_id: int = Path(..., ge=1),
) -> None:
    return await service.remove_image(product_id=product_id, image_id=image_id, admin_user=admin_user, background_tasks=background_tasks)




