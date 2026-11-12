import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

import httpx
import stripe

from app.core import config, enums, exceptions, redis_server
from app.models import Payment, PaymentProvider, User
from app.shared.utility import build_cache_key

from .payment_repository import PaymentRepository

stripe.api_key = config.settings.STRIPE_SECRET_KEY.get_secret_value()

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self, payment_repo: PaymentRepository):
        self.payment_repo = payment_repo


    
    """will add idempotency to this payment initialization"""
    async def initiate_stripe_payment(
        self, order_id: int, 
        current_user: User, shipping_address: dict, 
        order_number: str, total_amount: Decimal
        ) -> dict:
                
        stripe_shipping_payload = {
            "name": shipping_address["name"],
            "phone": shipping_address["contact_number"],
            "address": {
                "line1": shipping_address["street"],        # Mapped from 'street' field
                "city": shipping_address["city"],
                "state":shipping_address["state"],
                "country": str(shipping_address["country"]).upper(),     # Must be 2-letter ISO code (e.g., 'NG', 'US')
            }
        }
       
        
        # PAYMENT IDEMPOTENCY KEY (Derived from saved order attributes)
        idempotency_key = build_cache_key("stripe_payment", f"{order_id}", f"{order_number}")
    
        metadata={
        "order_id": str(order_id),
        "user_id": str(current_user.id),
        "idempotency_key": idempotency_key,
        "email": current_user.email,
        }
        
        cached = await redis_server.get_cache(idempotency_key)
        if cached:
            return cached

        try:
            intent = await stripe.PaymentIntent.create_async(
                amount=int((total_amount*100).quantize(Decimal(1), ROUND_HALF_UP)), # Convert to the smallest currency unit (e.g., kobo) and safely round using Decimal
                currency="ngn",
                metadata=metadata,
                receipt_email=current_user.email,
                payment_method_types=["card"],
                statement_descriptor_suffix=config.settings.PROJECT_NAME,
                shipping=stripe_shipping_payload,
                idempotency_key=idempotency_key,                 
            )
            
            existing_payment = await self.payment_repo.get_payment_by_order_id(order_id=order_id)
             
            # Update provider and references on the existing row when user change provider
            if existing_payment and existing_payment.provider != PaymentProvider.STRIPE:
                existing_payment.provider = PaymentProvider.STRIPE
                existing_payment.provider_reference = intent.id
                await self.payment_repo.update_payment(existing_payment)
 
            if not existing_payment:
                payment = Payment(
                    order_id=order_id,
                    amount=total_amount,
                    currency="ngn",
                    provider=PaymentProvider.STRIPE,
                    provider_reference=intent.id
                )
                await self.payment_repo.add_payment(payment)
                
            
            client_response = {
                "client_secret": intent.client_secret, 
                "payment_intent_id": intent.id
                }
            
            await redis_server.set_cache(key=idempotency_key, expire=86400, value=client_response)
            logger.info(f"Intent created for order: {order_id}: provider: stripe")
            return client_response
        except stripe.StripeError as e:
            logger.info(f"Stripe error occured: {e}")
            raise exceptions.BadRequestError(str(e))


    async def initiate_paystack_payment(
        self, 
        order_id: int, total_amount: Decimal, 
        current_user: User, shipping_address: dict, 
        order_number: str,
        ) -> dict:
        
        idempotency_key = build_cache_key("paystack_payment", f"{order_id}", f"{order_number}")
        cached = await redis_server.get_cache(idempotency_key)
        if cached:
            return cached
        
        payload = {
        "email": current_user.email,
        "amount": int((total_amount*100).quantize(Decimal(1), ROUND_HALF_UP)), # Convert to the smallest currency unit (e.g., kobo) and safely round using Decimal
        "currency": "NGN",
        "metadata": {
            "order_id": order_id,
            "user_id": current_user.id,
            "idempotency_key": idempotency_key,
            "email": current_user.email,
            
            # shipping adress can still be a plain string
            "custom_fields": [
            {
                "display_name": "Delivery Address",
                "variable_name": "delivery_address",
                "value": f"{shipping_address['street']}, {shipping_address['city']}, {shipping_address['state']}, {shipping_address['country']}"
            },
            {
                "display_name": "Customer details",
                "variable_name": "customer details",
                "value": f"name: {shipping_address['name']} Number:{shipping_address["contact_number"]}",
            },
            {
                "display_name": "Postal code",
                "variable_name": "postal code",
                "value": shipping_address["postal_code"]
            }
        ]
            },
        }

        reference = f"pay-{uuid.uuid4().hex[:10].upper()}"
        payload["reference"] = reference
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url="https://api.paystack.co/transaction/initialize",
                    headers={"Authorization": f"Bearer {config.settings.PAYSTACK_SECRET_KEY.get_secret_value()}"},
                    json=payload
                    )
                
                # Raise an exception for HTTP error codes (4xx, 5xx)
                response.raise_for_status()
                
                data = response.json()
                
                # Paystack-specific check: sometimes they return 200 OK with status: false
                if not data.get("status"):
                    raise exceptions.BadRequestError("Payment initialization failed")
                
        except httpx.TimeoutException:# Gateway Timeout (504)
            logger.error("Paystack timeout occured")
            raise exceptions.GatewayTimeoutError("Paystack request timed out. Please try again.")
            
        except httpx.RequestError as e:
            # Bad Gateway / Network error (502)
            logger.error(f"Paystack error occured {e}")
            raise exceptions.BadGatewayError(f"Could not connect to Paystack: {e}")
            
        except httpx.HTTPStatusError as e:
            # Third-party HTTP error
            logger.error(f"Paystack timeout occured {e.response.text}")
            raise exceptions.BadRequestError(f"Paystack error: {e.response.text}")
                        
        existing_payment = await self.payment_repo.get_payment_by_order_id(order_id=order_id) # if the previous payment is no longer active it creates a new one
        
        # Update provider and references on the existing row when user change provider
        if existing_payment and existing_payment.provider != PaymentProvider.PAYSTACK:
            existing_payment.provider = PaymentProvider.PAYSTACK
            existing_payment.provider_reference = data["data"]["reference"]
            await self.payment_repo.update_payment(existing_payment)  
            
        if not existing_payment:   
            payment = Payment(
                order_id=order_id,
                amount=total_amount,
                currency="ngn",
                provider=PaymentProvider.PAYSTACK,
                provider_reference=data["data"]["reference"],
            )
            await self.payment_repo.add_payment(payment)
        response = {
            "access_code": data["data"]["access_code"],
            "reference": data["data"]["reference"],
            "authorization_url": data["data"]["authorization_url"],  # not used by the popup flow, returned for reference
                }
        
        await redis_server.set_cache(key=idempotency_key, expire=7080, value=response) # TTL of 1 hr 58 mins
        logger.info(f"Access code created for order: {order_id}: provider: paystack")
        return response
        
    
    
    async def _update_payment_status(self, order_id: int, status: str, delete_idempotent_key: str) -> bool:
        
        db_payment = await self.payment_repo.get_payment_by_order_id(order_id)
        if not db_payment:
            logger.info(f"No payment for order_id:{order_id} found.")
            return True
        
        if db_payment.status == enums.PaymentStatus.FAILED:
            logger.warning(f"Webhook event occured for cancled payment of order_id:{order_id}")
            return True
        
        p_status = [enums.PaymentStatus.PENDING, enums.PaymentStatus.FAILED]
        
        if db_payment.status in p_status and status == "success":    
            db_payment.status = enums.PaymentStatus.COMPLETED
        
        await self.payment_repo.update_payment(db_payment)
        
        if status == "success":
            await redis_server.delete_cache(delete_idempotent_key)
        return True
    
    
    async def get_payment_by_id_or_refrence(
        self, 
        payment_id: int | None = None, 
        provider_reference: str | None = None,
        order_id: int | None = None
        ) -> Payment:
        
        """
        Here a payment can be quired by the provider refrence, payment_id or order_id
        at lease one query at a time
        """
        
        if payment_id is None and provider_reference is None and order_id is None:
            raise exceptions.BadRequestError("Cannot accept an empty request.")
        
        payment = await self.payment_repo.get_by_id_or_refrence(payment_id=payment_id, provider_reference=provider_reference, order_id=order_id)
        
        if not payment:
            raise exceptions.NotFoundError("Payment not found")
        
        return payment

    async def list_payments(self, page: int, page_size: int, provider: str | None = None) -> dict:
        
        skip = (page - 1) * page_size
        payments, count =  await self.payment_repo.get_all_payment(skip=skip, limit=page_size, provider=provider)
        
        total_pages = ceil(count / page_size) if count > 0 else 0
        
        return {
            "payments": payments,
            "page": page,
            "page_size": page_size,
            "count": count,
            "total_pages": total_pages
        }
        
    
    async def delete_payment(self, payment_id: int) -> bool:
        
        delete = await self.payment_repo.delete_payment(payment_id)
        if not delete:
            raise exceptions.NotFoundError("Payment not found")
        
        return True
    
    