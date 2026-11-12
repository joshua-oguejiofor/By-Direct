

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.depends import current_user, di_injection
from app.models.user import User

from .order_schema import (
    CheckoutRequest,
    OrderResponse,
    OrderStatusAuditRead,
    OrderWithItemsResponse,
)
from .order_service import OrderService

router = APIRouter()

current_user_ = Annotated[User, Depends(current_user.get_current_user)]
admin_user_ = Annotated[User, Depends(current_user.get_admins)]

order_service_ = Annotated[OrderService, Depends(di_injection.get_order_service)]


@router.post("/", status_code=200)
async def checkout(
    request: Request,
    data: CheckoutRequest,
    current_user: current_user_,
    service: order_service_,
):
    return await service.checkout(request=request, current_user=current_user, data=data)


@router.get("/", status_code=200, response_model=OrderResponse)
async def list_orders(
    admin_user: admin_user_,
    service: order_service_,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    
    return await service.get_all_orders(page=page, page_size=page_size)


@router.get("/me", response_model=OrderResponse, status_code=200)
async def my_orders(
    current_user: current_user_,
    service: order_service_,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50)
):
    
    """Retrieve order history for the authenticated user, newest first."""
    return await service.get_my_orders(current_user=current_user, page=page, page_size=page_size)


@router.get("/{order_id}/payment", response_model=OrderWithItemsResponse, status_code=200) 
async def get_order(
    current_user: current_user_,
    service: order_service_,
    order_id: int = Path(..., ge=1),
    
):
    """View an order with it items and payment details"""
    return await service.get_order_by_id(order_id, current_user)


@router.patch("/{order_id}/status", status_code=200)
async def update_order_status(
    data: OrderStatusAuditRead,
    current_user: current_user_,
    service: order_service_,
    order_id: int = Path(..., ge=1),
) -> dict[str, str]:
    
    """Update the status of an order (e.g.,cancled confirmed, shipped, delivered)"""
    await service.change_order_status(order_id=order_id, new_status=data.new_status, current_user=current_user, reason=data.reason)
    return {"msg":"Order status updated successfully"}

