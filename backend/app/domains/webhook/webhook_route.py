from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.depends import current_user, di_injection
from app.domains.webhook.webhook_service import WebookEventService
from app.models.user import User

router = APIRouter()

current_user_ = Annotated[User, Depends(current_user.get_current_user)]
webhook_service = Annotated[WebookEventService, Depends(di_injection.get_webhook_service)]



@router.post("/stripe", status_code=200)
async def stripe_webhook(
    request: Request, 
    service: webhook_service,
    background_task: BackgroundTasks
    ):
    
    await service.handle_stripe_webhook(request=request, background_task=background_task)
    return {"status": "ok"}



@router.post("/paystack", status_code=200)
async def paystack_webhook(
    request: Request, 
    service: webhook_service,
    background_task: BackgroundTasks
    ):
    
    await service.handle_paystack_webhook(request=request, background_task=background_task)
    return {"status": "ok"}

