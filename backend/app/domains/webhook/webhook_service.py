import hashlib
import hmac
import logging

import stripe
from fastapi import BackgroundTasks, Request

from app.core import config, exceptions, redis_server
from app.core.config import settings
from app.domains.order.order_service import OrderService
from app.domains.payment.payment_service import PaymentService
from app.shared.utility import build_cache_key

stripe.api_key = config.settings.STRIPE_SECRET_KEY.get_secret_value()


logger = logging.getLogger(__name__)



class WebookEventService:
    def __init__(self, payment_service: PaymentService, order_service: OrderService = None):
        self.payment_service = payment_service
        self.order_service = order_service



    # Done
    async def handle_stripe_webhook(self, request: Request, background_task: BackgroundTasks) -> bool:
        """Seprating the try except helps in maintainance(specify where the error came from)"""
        payload = await request.body()
        header_signature = request.headers.get("stripe-signature")
        
        if not header_signature:
            raise exceptions.BadRequestError("Missing stripe-signature header") 
              
        try:
            event = stripe.Webhook.construct_event(
                payload, 
                header_signature, 
                config.settings.STRIPE_WEBHOOK_SECRET.get_secret_value()
                )
        except (ValueError, stripe.SignatureVerificationError):
            logger.exception("stripe webhook construct event failed")
            raise exceptions.BadRequestError("Invalid signature") 
        
        try:
            # webhook idempotency       
            event_idempotent_key = build_cache_key("stripe_evt", f"{event["id"]}")
            event_value = f"status:{event['type']}"
            
            if await redis_server.get_cache(event_idempotent_key):
                return True
            
            payload = event["data"]["object"].to_dict()
            
            if not isinstance(payload, dict):
                logger.info("Recieved an unknown event metadata")
                return True 
            
            event_id = payload.get("id")
            # Safely extract metadata with fallback guards
            paid_amount = payload.get("amount_received", 0)
            currency = payload.get("currency")
            metadata = payload.get("metadata", {})
            
            if not isinstance(metadata, dict):
                logger.info("Recieved an unknown event metadata")
                return True    
            
            order_id = metadata.get("order_id")
            user_id = metadata.get("user_id")
            payment_idemoptency = metadata.get("idempotency_key")
            user_email = metadata.get("email")
            
            if (
                not order_id or not str(order_id).isdigit()
                or not user_id or not user_email 
                or not payment_idemoptency 
                # or not order_number  
                or currency not in ["ngn", "NGN"]        
            ):
                logger.warning(f"Invalid stripe metadata in event: {event_id}")
                return True
            
            if event["type"] == "payment_intent.succeeded" or  event["type"] == "charge.succeeded":
                result = await self.order_service.fulfill_order_status(
                    order_id=int(order_id), status="success", 
                    user_id=int(user_id), email=user_email, 
                    background_task=background_task, 
                    paid_amount=paid_amount,
                    )
                if result == "confirmed":
                    await self.payment_service._update_payment_status(
                        order_id=int(order_id), status="success", delete_idempotent_key=payment_idemoptency
                        )   
                    await redis_server.set_cache(key=event_idempotent_key, value=event_value, expire=86400) # set the webhook idempotency
                    
                else:
                    # result in ("underpaid", "late"):
                    logger.error(f"MONEY RECEIVED FOR ORDER: {order_id} BUT WAS {result}")
                
                
            
            
            elif event["type"] in settings.FAILED_EVENTS:
                payload = event["data"]["object"]
        
                # Extract the failure reason from last_payment_error
                last_error = payload.get("last_payment_error") or {}
                failure_message = last_error.get("message", "Payment failed with an unknown error")
                decline_code = last_error.get("decline_code") # e.g., "insufficient_funds", "card_declined"
                logger.info(f"Stripe payment failed for order_id:{order_id}. Reason: {failure_message}. decline-code: {decline_code}")
                
                
            return True
        except Exception:  
            logger.exception(f"Unhandled error for stripe webhook-event handler. event:{event["id"]}")
            raise exceptions.AppException("Webhook processing failed")
        
    
    async def handle_paystack_webhook(self, request: Request, background_task: BackgroundTasks) -> bool:
        
        body = await request.body()
        signature = request.headers.get("x-paystack-signature", "")

        paystack_key = settings.PAYSTACK_SECRET_KEY.get_secret_value()
        expected = hmac.new(paystack_key.encode(), body, hashlib.sha512).hexdigest()
        
        if not hmac.compare_digest(expected, signature):
            raise exceptions.BadRequestError("Invalid paystack signature")
            
        try:

            event = await request.json()
            
            payload = event["data"]
            
            if not isinstance(payload, dict):
                logger.info("Recieved an unknown event metadata")
                return True 
            
            event_id = payload.get("id")
            paid_amount = payload.get("amount")
            currency = payload.get("currency")
            
            metadata = payload.get("metadata")
            
            if not isinstance(metadata, dict):
                logger.info("Recieved an unknown event")
                return True   
            
            order_id = metadata.get("order_id")
            payment_idempotency_key = metadata.get("idempotency_key")
            user_id = metadata.get("user_id")
            user_email = metadata.get("email")
            
            if(
                not order_id or not payment_idempotency_key 
                or not user_id or not user_email
                or currency not in ["ngn", "NGN"]
            ):
                logger.warning(f"Invalid paystack metadata in event: {event_id}")
                return True

            event_idempotent_key = build_cache_key("paystack_event", str(order_id))
            
            cached = await redis_server.get_cache(event_idempotent_key)
            if cached == "charge.success":
                return True
        
            if event["event"] == "charge.success":            
                logger.info(f"Payment successfull for order: {order_id}")
                
                result = await self.order_service.fulfill_order_status(
                    paid_amount=paid_amount,
                    order_id=order_id, status="success", 
                    user_id=user_id, email=user_email, 
                    background_task=background_task
                    )
                if result == "confirmed":
                    await self.payment_service._update_payment_status(
                        order_id=order_id, status="success", delete_idempotent_key=payment_idempotency_key
                        )   
                    await redis_server.set_cache(key=event_idempotent_key, value=event["event"], expire=86400)
                return True
                
            elif event["event"] == "charge.failed":
                
                gateway_response = event["data"]["gateway_response"]
                reference = event["data"]["reference"]
                logger.info(f"Paystack payment failed for order_id:{order_id} reference: {reference}. Reason: {gateway_response}")
                
            return  True
        except Exception:  
            logger.exception("Unhandled error for paystack webhook-event handler")
            raise exceptions.AppException("Webhook processing failed")








# stripe trigger payment_intent.succeeded
# stripe listen --forward-to localhost:8000/api/v1/payments/webhook

# to trigger a payment webook event
# stripe post payment_intents \
#   -d amount=60000000000000 \
#   -d currency=ngn \
#   -d "metadata[order_id]=22" \
#   -d "metadata[user_id]=10" \
#   -d "automatic_payment_methods[enabled]=true"