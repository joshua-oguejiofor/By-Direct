from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.depends import current_user, di_injection
from app.models import User

from .category_schema import AddCategory, CategoryResponse
from .category_service import CategoryService

router = APIRouter()

category_service_ = Annotated[CategoryService, Depends(di_injection.get_category_service)]
admin_user = Annotated[User, Depends(current_user.get_admins)]
superadmin_user = Annotated[User, Depends(current_user.get_superadmin)]



@router.post("/", status_code=201)
async def create_category(
    data: AddCategory, 
    service: category_service_,
    admin_user: admin_user,
) -> dict[str, str]:
    
    """Admin only. Create a new product category with optional parent for subcategory nesting."""
    await service.create_category(data=data, admin_user=admin_user)
    return {"msg":"Category created successfully."}


@router.get("/", response_model=list[CategoryResponse], status_code=200)
async def list_categories(service: category_service_):
    
    return await service.get_all_categories()


@router.get("/{category_id}", response_model=CategoryResponse, status_code=200)
async def get_category(
    service: category_service_,
    category_id: int = Path(..., ge=1), 
    ):
    """Retrieve a single category by ID."""
    
    return await service.get_category_by_id(category_id)

@router.patch("/{category_id}", status_code=200)
async def update_category(
    data: AddCategory,
    service: category_service_,
    admin_user: admin_user,
    category_id: int = Path(..., ge=1)
) -> dict[str, str]:
    
    await service.update_category(category_id=category_id, data=data, admin_user=admin_user)
    return {"msg":"Category updated successfully."}


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    superadmin_user: superadmin_user,
    service: category_service_,
    category_id: int = Path(..., ge=1),  
):
    
    """Admin only. Soft-delete a category by marking it inactive."""
    await service.remove_category(category_id=category_id, superadmin_user=superadmin_user)
    return {"msg":"Category deleted successfully."}
