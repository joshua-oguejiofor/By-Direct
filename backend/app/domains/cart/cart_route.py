from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.depends import current_user, di_injection
from app.depends.visitor import read_guest_id, visitor_
from app.models.user import User

from .cart_schema import CartItemAdd, CartResponse
from .cart_service import CartService
from .guest_cart_service import GuestCartService

router = APIRouter()

current_user_ = Annotated[User, Depends(current_user.get_current_user)]
cart_service_ = Annotated[CartService, Depends(di_injection.get_cart_service)]
guest_cart_ = Annotated[GuestCartService, Depends(di_injection.get_guest_cart_service)]

# Every route below works for BOTH logged-in users (database cart) and guests (Redis cart).
# No return annotation on purpose: a user gets an ORM Cart, a guest gets a dict.


@router.get("/", status_code=200, response_model=CartResponse)
async def get_cart(
    visitor: visitor_, 
    service: cart_service_, 
    guest: guest_cart_
    ):
    
    if visitor.user:
        return await service.get_cart_with_items(visitor.user.id)
    return await guest.get_cart_with_items(visitor.guest_id)


@router.post("/items", status_code=201)
async def add_to_cart(
    data: CartItemAdd, 
    visitor: visitor_, 
    service: cart_service_, 
    guest: guest_cart_
    ) -> dict[str, str]:
    
    if visitor.user:
        return await service.add_item(visitor.user, data)
    return await guest.add_item(visitor.guest_id, data)


@router.delete("/items/{item_id}", status_code=204)
async def remove_from_cart(
    visitor: visitor_, 
    service: cart_service_, 
    guest: guest_cart_,
    item_id: int = Path(..., ge=1),
):
    """For a logged-in user item_id is the cart item id. For a guest it is the product id."""
    if visitor.user:
        return await service.remove_item(visitor.user, item_id)
    return await guest.remove_item(visitor.guest_id, item_id)


@router.delete("/", status_code=204)
async def clear_cart(
    visitor: visitor_, 
    service: cart_service_, 
    guest: guest_cart_
    ):
    
    if visitor.user:
        return await service.clear_cart(visitor.user.id)
    else:
        return await guest.clear_cart(visitor.guest_id)


@router.post("/merge", status_code=200)
async def merge_guest_cart(
    request: Request,
    current_user: current_user_, service: cart_service_, guest: guest_cart_,
) -> dict[str, int]:
    
    """Call once right after login. Moves the guest cart into the user's cart."""
    guest_id = read_guest_id(request)
    if guest_id is None:
        return {"merged": 0, "skipped": 0}
    return await guest.merge_into_user(guest_id, current_user, service)
