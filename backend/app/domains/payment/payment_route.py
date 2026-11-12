from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.enums import PaymentProvider
from app.depends import current_user, di_injection
from app.models.user import User

from .payment_schema import PaymentResponse, PaymentResponseList
from .payment_service import PaymentService

router = APIRouter(dependencies=[Depends(current_user.get_admins)])

super_admin = Annotated[User, Depends(current_user.get_superadmin)]
payment_service_ = Annotated[PaymentService, Depends(di_injection.get_payment_service)]



@router.get(
    "/", 
    response_model=PaymentResponse, 
    status_code=200, 
    description="Here a payment can be quired by the provider refrence, payment_id or order_id at lease one query at a time"
    )
async def get_payment(
    service: payment_service_,
    provider_refrence: str | None = Query(None),
    payment_id: int | None = Query(None, ge=1), 
    order_id: int | None = Query(None, ge=1),
):
    return await service.get_payment_by_id_or_refrence(payment_id=payment_id, provider_reference=provider_refrence, order_id=order_id)



@router.get("/all", response_model=PaymentResponseList, status_code=200, description="List of payment, can also be filtered by the payment provider")
async def get_all_payments(
    service: payment_service_,
    provider: PaymentProvider | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
        ):
    
    """Retrieve a paginated list of payments """
    return await service.list_payments(page=page, page_size=page_size, provider=provider)


@router.delete("/{payment_id}", status_code=204, description="Hard deletion can be done only by super-admin")
async def delete_payment(
    super_admin: super_admin,
    service: payment_service_,
    payment_id: int = Path(..., ge=1), 
):
    """Get payment status and details for a specific order."""
    return await service.delete_payment(payment_id)




