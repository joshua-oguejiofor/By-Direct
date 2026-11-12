from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.depends import current_user, di_injection
from app.depends.visitor import optional_user_
from app.models.user import User

from .review_schema import ReviewCreate, ReviewlistResponse
from .review_service import ReviewService

router = APIRouter()


review_service_ = Annotated[ReviewService, Depends(di_injection.get_review_service)]
current_user_ = Annotated[User, Depends(current_user.get_current_user)]
admin_user_ = Annotated[User, Depends(current_user.get_admins)]
superadmin_user = Annotated[User, Depends(current_user.get_superadmin)]
optioanl_user = Annotated[User | None, Depends(optional_user_)]

@router.post("/", status_code=201)
async def create_review(
    data: ReviewCreate,
    current_user: current_user_,
    service: review_service_
) -> dict[str, str]:
    
    await service.create_review(current_user=current_user, data=data)
    return {"msg":"Review added successfully"}


@router.get("/", response_model=ReviewlistResponse, status_code=200)
async def get_product_reviews(
    service: review_service_,
    current_user: optional_user_,
    product_id: int = Query(..., ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=10, description="Amount of reviews per page"),
):
    return await service.get_product_reviews(
        current_user=current_user,product_id=product_id, page=page, page_size=page_size
        )



@router.patch("/{review_id}/approve", status_code=200)
async def approve_review(
    admin_user: admin_user_,
    service: review_service_,
    review_id: int = Path(..., ge=1)
) -> dict[str, str]:
    
    return await service.approve_review(review_id=review_id, admin_user=admin_user)
   

@router.delete("/{review_id}", status_code=204)
async def delete_review(
    admin_user: admin_user_,
    service: review_service_,
    review_id: int = Path(..., ge=1)
    ) -> None:
    
    return await service.delete_review(review_id=review_id, admin_user=admin_user)
   