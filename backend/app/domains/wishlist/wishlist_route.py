from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.depends import current_user, di_injection
from app.depends.visitor import read_guest_id, visitor_
from app.models.user import User

from .guest_wishlist_service import GuestWishlistService
from .wishlist_service import WishlistService

router = APIRouter()

current_user_ = Annotated[User, Depends(current_user.get_current_user)]
wishlist_service = Annotated[WishlistService, Depends(di_injection.get_wishlist_service)]
guest_wishlist_ = Annotated[GuestWishlistService, Depends(di_injection.get_guest_wishlist_service)]

# Works for BOTH logged-in users (database) and guests (Redis).


@router.get("/", status_code=200)
async def get_wishlist(
    visitor: visitor_, 
    service: wishlist_service, 
    guest: guest_wishlist_
    ):
    if visitor.user:
        return await service.get_wishlist(visitor.user)
    return await guest.get_wishlist(visitor.guest_id)


@router.post("/items/{product_id}", status_code=201)
async def add_to_wishlist(
    visitor: visitor_, 
    service: wishlist_service, 
    guest: guest_wishlist_,
    product_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
) -> dict[str, str]:
    
    if visitor.user:
        await service.add_wishlist(current_user=visitor.user, product_id=product_id)
    else:
        await guest.add_wishlist(visitor.guest_id, product_id)
    return {"msg": "Added to wishlist"}


@router.delete("/items/{product_id}", status_code=204)
async def remove_from_wishlist(
    visitor: visitor_, 
    service: wishlist_service, 
    guest: guest_wishlist_,
    product_id: int = Path(..., ge=1),
):
    if visitor.user:
        return await service.remove_wishlist_item(current_user=visitor.user, product_id=product_id)
    return await guest.remove_wishlist_item(visitor.guest_id, product_id)


@router.post("/merge", status_code=200)
async def merge_guest_wishlist(
    request: Request,
    current_user: current_user_, 
    service: wishlist_service, 
    guest: guest_wishlist_,
) -> dict[str, int]:
    """Call once right after login. Moves the guest wishlist into the user's wishlist."""
    guest_id = read_guest_id(request)
    if guest_id is None:
        return {"merged": 0, "skipped": 0}
    result = await guest.merge_into_user(guest_id, current_user, service)
    return result
