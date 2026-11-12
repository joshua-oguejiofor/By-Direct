from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.enums import UserRole
from app.depends import current_user, di_injection
from app.models.user import User

from .user_schema import ProfileResponse, UpdateProfile, UserListResponse, UserProfile
from .user_service import UserService

router = APIRouter()

admin_user = Annotated[User, Depends(current_user.get_admins)]
current_user_ = Annotated[User, Depends(current_user.get_current_user)]
user_service_ = Annotated[UserService, Depends(di_injection.get_user_service)]



@router.post("/me/profile", status_code=201)
async def add_profile(
    data: UserProfile,
    current_user: current_user_,
    service: user_service_,
)-> dict[str, str]:
    
    await service.create_profile(current_user=current_user, data=data)
    return {"msg":"Profile created successfully."}


@router.get("/all", status_code=200, response_model=UserListResponse)
async def list_all_users(
    current_user: admin_user,
    service: user_service_,
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=50),
    
):
    """Admin only. List all registered users with pagination."""
    return await service.all_users(page=page, page_size=page_size)

@router.patch("/me", status_code=200)
async def update_profile(
    data: UpdateProfile,
    current_user: current_user_,
    service: user_service_,
) -> dict[str, str]:
    
    await service.update_my_profile(current_user=current_user, data=data)
    return {"msg":"Profile updated successfully."}
    

@router.get("/search", response_model=UserListResponse, status_code=200)
async def search_users(
    current_user: admin_user,
    service: user_service_,
    search: str | None = Query(None, description="Search by name or email"),
    role: UserRole | None = Query(None, description="Filter by user role"),  # noqa: B008
    is_active: bool | None = Query(None, description="Filter active/inactive users"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    
):
    return await service.search_users(
        search=search, 
        role=role, 
        is_active=is_active, 
        page=page, 
        page_size=page_size
    )


@router.get("/{user_id}", response_model=ProfileResponse, status_code=200)
async def get_profile(
    current_user: current_user_,
    service: user_service_,
    user_id: int | None = Path(ge=1)
    
):
    return await service.user_profile(current_user=current_user, user_id=user_id)
    

@router.delete("/{user_id}", status_code=200)
async def deactivate_account(
    current_user: current_user_,
    service: user_service_,
    user_id: int | None = Path(ge=1),
)-> dict[str, str]:
    
    return await service.deactivate_user_account(user_id=user_id, current_user=current_user)
