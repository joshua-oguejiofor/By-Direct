import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from fastapi import BackgroundTasks, Request

from app.core import exceptions, redis_server
from app.core.config import settings
from app.core.enums import OrderStatus, PaymentProvider, PaymentStatus
from app.depends.visitor import read_idempotency_key
from app.domains.cart.cart_service import CartService
from app.domains.payment.payment_service import PaymentService
from app.domains.product.product_service import ProductService
from app.domains.user.user_service import UserService
from app.models import User
from app.models.order import Order, OrderItem, OrderStatusAudit
from app.shared.utility import admin_check, build_cache_key, optimize_prize
from app.workers.dispatch_task import dispatch_order_comfirmation

from .order_repository import OrderRepository
from .order_schema import CheckoutRequest

logger = logging.getLogger(__name__)



class OrderService:
    def __init__(
        self, 
        order_repo: OrderRepository, 
        product_service: ProductService = None, 
        cart_service: CartService = None, 
        payment_service: PaymentService = None,
        user_service: UserService = None
    ):
        self.order_repo = order_repo
        self.product_service = product_service
        self.cart_service = cart_service
        self.payment_service = payment_service
        self.user_service = user_service
        
        
    @staticmethod
    def _full_name(profile) -> str:
        """This helps format the user's name, removing None and extra space"""
        parts = [profile.first_name, profile.last_name]
        return " ".join(p.strip() for p in parts if p and p.strip())
        
    async def _initiate_paymment(
        self, order_number: str,
        payment_provider: PaymentProvider, 
        order_id: int, current_user: User, 
        shipping_address: dict, total_amount: Decimal
        ) -> dict[str, str]:
        
        if payment_provider == PaymentProvider.STRIPE:      
            return await self.payment_service.initiate_stripe_payment(
                order_id=order_id,
                current_user=current_user,
                shipping_address=shipping_address,
                order_number=order_number,
                total_amount=total_amount,
                
            )
        elif payment_provider == PaymentProvider.PAYSTACK:
            return await self.payment_service.initiate_paystack_payment(
                order_id=order_id,
                order_number=order_number,
                current_user=current_user,
                shipping_address=shipping_address,
                total_amount=total_amount,  
            )
        else:
            raise exceptions.BadRequestError("Invalid payment provider.")
        
        
    # Checkout handler with dual-layer idempotency protection.
    async def checkout(self, current_user: User, data: CheckoutRequest, request: Request) -> dict[str, str]:
        
        
        if data.name is None or data.contact_number is None:
            
            try:
                profile = await self.user_service.user_profile(current_user=current_user, user_id=current_user.id)
            except exceptions.NotFoundError:
                raise exceptions.BadRequestError("Name and contact number are required. None was detected for both profile and checkout details.")
        
        name = data.name if data.name else self._full_name(profile)
        contact_number = data.contact_number if data.contact_number else profile.phone_number
        
        if not name or not contact_number:
            raise exceptions.BadRequestError("Name and contact number are required. None was detected for both profile and checkout details.")
        
        order_shipping_address = {
            "name": name,
            "street": data.shipping_address.street,
            "city": data.shipping_address.city,
            "state": data.shipping_address.state,
            "postal_code": data.shipping_address.postal_code,
            "country": data.shipping_address.country,
            "notes": data.notes,
            "payment_provider": data.payment_provider,
            "contact_number": contact_number
            }
        
        idempotency_key = read_idempotency_key(request)
        
        redis_checkout_key = build_cache_key("checkout_lock", f"{current_user.id}", idempotency_key)
    
        # Check if this exact checkout attempt already created a pending order
        existing_order_id = await redis_server.get_cache(redis_checkout_key)
        
        if existing_order_id:
            existing_order = await self.order_repo.get_by_order_id(int(existing_order_id))
            
            if (
                existing_order and existing_order.user_id == current_user.id
                and existing_order.status == OrderStatus.PENDING 
                and existing_order.expiration_cutoff >= datetime.now(UTC).replace(tzinfo=None) # tempory, will remove when new data enters db
                ):
                # Return the existing order immediately — skips stock decrement!
                logger.info(f"Duplicate checkout request detected for user {current_user.id}. Returning existing order {existing_order.id}.")
                
                return await self._initiate_paymment(
                    order_id=existing_order.id,
                    current_user=current_user,
                    shipping_address=existing_order.shipping_address,
                    payment_provider=data.payment_provider,
                    order_number=existing_order.order_number,
                    total_amount=existing_order.total_amount
                    
                )
        
        # CART VALIDATION & STOCK DEDUCTION
        user_cart = await self.cart_service._get_cart(current_user.id)
        if not user_cart or not user_cart.items:
            raise exceptions.BadRequestError("Cart is empty")
        
        # Use Decimal for financial accuracy instead of float
        subtotal = Decimal("0.00")
        order_items = []

        for item in user_cart.items:
            reserved = await self.product_service.reserve_stock_for_user(product_id=item.product_id, quantity=item.quantity)
            
            if reserved == 0: # affected row count from database
                low_product = await self.product_service.get_product_by_id(item.product_id, current_user)
                logger.info(f"Insufficent product:{item.product_id} for user: {current_user.id} order")
                product_name = low_product["name"] if isinstance(low_product, dict) else low_product.name
                raise exceptions.BadRequestError(f"Insufficient stock for {product_name}")
                
            product = await self.product_service._get_product_with_id(item.product_id, current_user=None)
            
            # Ensure price is handled as a Decimal
            price = Decimal(str(optimize_prize(product)))
            
            total = price * item.quantity
            subtotal += total  # Clean Decimal addition
            
            order_items.append(
                OrderItem(
                    product_id=product.id,
                    quantity=item.quantity,
                    unit_price=price,
                    total_price=total,
                    product_name=product.name,
                )
            )
            
        # Precise Decimal calculations for tax and shipping
        tax = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
        shipping = Decimal("10.00")
        total_amount = subtotal + tax + shipping

        reserve_expiration = (
            timedelta(hours=1, minutes=55) 
            if data.payment_provider == PaymentProvider.PAYSTACK 
            else timedelta(hours=2) 
            )
        
        expiration_cutoff = datetime.now(UTC) + reserve_expiration
        order = Order(
            user_id=current_user.id,
            order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}",
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            tax_amount=tax,
            shipping_amount=shipping,
            total_amount=total_amount,
            shipping_address=order_shipping_address,
            notes=data.notes,
            contact_number=contact_number, 
            items=order_items,
            expiration_cutoff=expiration_cutoff
        )
        
        saved_order = await self.order_repo.save_order(order)

        # Build the redis TTL based on the service provider (stripe 2 hrs, paystack 1:55 min)
        redis_expiration = 86400 if data.payment_provider == PaymentProvider.STRIPE else 7080
        await redis_server.set_cache(key=redis_checkout_key, value=saved_order.id, expire=redis_expiration)
        logger.info(f"Order created for: {current_user.id}: order_id: {order.id}")
        await redis_server.bump_product_cache_version() # eliminating stale cached data in redis

        return await self._initiate_paymment(
            payment_provider=data.payment_provider,
            order_id=saved_order.id,
            current_user=current_user,
            shipping_address=order_shipping_address,
            order_number=saved_order.order_number,
            total_amount=saved_order.total_amount,
                
            )
        
    async def get_my_orders(self, current_user: User, page: int, page_size: int):
        skip = (page - 1) * page_size
        
        orders, total_count = await self.order_repo.my_orders(current_user.id, skip=skip, limit=page_size)
        # Compute total pages safely (handling division by zero or empty results)
        total_pages = ceil(total_count / page_size) if total_count > 0 else 0
        
        return {
            "orders": orders,
            "page": page,
            "page_size": page_size,
            "count": total_count,
            "total_pages": total_pages,            
            }   
             

    async def get_all_orders(self, page: int, page_size: int):
        skip = (page - 1) * page_size
        
        orders, total_count = await self.order_repo.all_orders(skip=skip, limit=page_size)
        
        total_pages = ceil(total_count /  page_size) if total_count > 0 else 0
        
        return {
            "orders": orders,
            "page": page,
            "page_size": page_size,
            "count": total_count,
            "total_pages": total_pages,
            }        
    

    async def get_order_by_id(self, order_id, current_user: User):
        order = await self.order_repo.get_with_items(order_id)
        if not order:
            raise exceptions.NotFoundError("Order not found")
        
        if order.user_id != current_user.id and current_user.role not in settings.ADMINS:
            raise exceptions.ForbiddenError("Unable to access")
        
        return order


    # This will be called by webhook service to fulfill order status.
    async def fulfill_order_status(
        self, 
        order_id: int, paid_amount: int,
        status: str, user_id: int, 
        email: str, background_task: BackgroundTasks, 
        )-> str:
        
        """This will be called by webhook service to fulfill order status."""
        order = await self.order_repo.get_with_items(order_id)
        
        old_status = order.status
    
        if not order:
            logger.info(f"Order of order_id: {order_id} not found to confirm payment ")
            return "Not found"
        
        if order.status == OrderStatus.CANCELLED:
            logger.info(f"Late order fulfillment for order:{order.id}")
            return "Late"
        
        if order.status in settings.VERIFY_USER_PURCHASE:
            logger.info(f"Order for {order.id} has already being verified.")
            return "Ignored"
        
        # Safely convert Decimal order total to minor units (cents) as an integer
        expected_amount = int((order.total_amount * Decimal(100)).quantize(Decimal(1), ROUND_HALF_UP))
        
        if paid_amount < expected_amount:
            logger.error(f"Underpayment on Order {order.id}. Paid: {paid_amount}, Expected: {expected_amount}")
            return "Underpaid"
        
        if status == "success" and order.status == OrderStatus.PENDING:   
            
            order.status = OrderStatus.CONFIRMED
            
            audit_entry = OrderStatusAudit(
                order_id=order.id,
                old_status=old_status,
                new_status=OrderStatus.CONFIRMED,
                changed_by_user_id=None,
                reason="system:webhook",
            )
            await self.order_repo.save_order(audit_entry)
            
            serialized_items = [
                {
                    "product_name": item.product_name, 
                    "quantity": item.quantity, 
                    "price": Decimal(item.unit_price), 
                    } for item in order.items
                            ]
            
            await self.order_repo.update_order(order)
            
            background_task.add_task(dispatch_order_comfirmation, email=email, order_number=order.order_number, total_amount=order.total_amount, items=serialized_items)
            
            await self.cart_service.clear_cart(user_id) 
            """will send order confirmation here to the user."""           
        
            return "confirmed"
        
   
    async def _restock_pre_ordered_items(
        self, 
        order: Order, 
        reason: str,
        user_id: int | None = None,
        
        ) -> bool:
        
        for item in order.items:
            if item.product_id is None:
                continue
            
            # Atomic bulk update at DB level to avoid race conditions
            await self.product_service.restock_product(product_id=item.product_id, quantity=item.quantity)
                
        old_status = order.status
        # Mark the order as EXPIRED
        order.status = OrderStatus.CANCELLED
            
            
        if order.payment:
            order.payment.status = PaymentStatus.CANCELLED
        await self.order_repo.update_order(order)
        
        # Record the audit entry
        audit_entry = OrderStatusAudit(
            order_id=order.id,
            old_status=old_status,
            new_status=OrderStatus.CANCELLED,
            changed_by_user_id=user_id,
            reason=reason,
        )
        await self.order_repo.save_order(audit_entry)

        await redis_server.bump_product_cache_version()
        return True
        
        
    async def _release_expired_orders(self) -> None | bool:
        """
        Asynchronous core worker logic executing row-level locking,
        stock release, and order state transition in a single atomic transaction.
        """
        # 1. Fetch expired PENDING orders with row-level locks
        # 'with_for_update(skip_locked=True)' prevents concurrent workers or webhooks 
        # from blocking or executing conflicting updates on the same row.
        
        expiration_cutoff = datetime.now(UTC)
        status = OrderStatus.PENDING
        expired_orders = await self.order_repo.check_expired_order(order_status=status, expire=expiration_cutoff)
        
        if not expired_orders:
            logger.info("No expired pending orders found.")
            return None

        expired_order_ids = []

        # Iterate through orders and restore stock quantities
        for order in expired_orders:
            expired_order_ids.append(order.id)
            
            reason = "System:order-expired"
            await self._restock_pre_ordered_items(order=order, reason=reason)
            
        logger.info(
            f"Successfully expired {len(expired_orders)} orders with it relative Payment"
            f"and released stock. Order IDs: {expired_order_ids}"
        )
        
        return True
    
    
    # Order state machine e.g. confirmed->processing->shipped->delivered, and reject others with 409.
    async def change_order_status(
    self, order_id, new_status: OrderStatus, 
    current_user: User, reason: str | None = None
    ) -> bool:
        
        is_admin = admin_check(current_user)
    
        db_order = await self.order_repo.get_with_items(order_id)
        if not db_order:
            raise exceptions.NotFoundError("Order not found.")
        
        if db_order.user_id != current_user.id and current_user.role not in settings.ADMINS:
            raise exceptions.ForbiddenError("Cannot access")
        
        # Customers may only cancel their own PENDING order. Anything else is admin-only.
        if not is_admin:
            if new_status != OrderStatus.CANCELLED:
                raise exceptions.ForbiddenError("Only an admin can change the order status.")
            if db_order.status != OrderStatus.PENDING:
                raise exceptions.ForbiddenError("You can only cancel an order that is still pending.")

        
        current_status = db_order.status
            
        # Prevent setting the exact same status
        if current_status == new_status:
            raise exceptions.ConflictingError(f"Order is already in status '{current_status}'.")
        
        # Enforce the state machine transition rules setting a one way status change
        if new_status not in settings.ALLOWED_TRANSITIONS.get(current_status, set()):
            raise exceptions.ConflictingError(
                f"Invalid status transition from '{current_status}' to '{new_status}'."
            )
        # 2 FA
        if new_status == OrderStatus.CANCELLED:
            if (
                # current_user.role not in settings.ADMINS 
                not is_admin and 
                not (
                    new_status == OrderStatus.CANCELLED 
                    and db_order.user_id == current_user.id 
                    and current_status == OrderStatus.PENDING
                    )
                ): 
                raise exceptions.ForbiddenError("Unable to cancle this order")
            added_reason = "user no longer instrested" if reason is None else reason
            return await self._restock_pre_ordered_items(
                order=db_order, reason=added_reason, user_id=current_user.id
                )
        

        old_status = current_status
        db_order.status = new_status
        
        # Record the audit entry
        audit_entry = OrderStatusAudit(
            order_id=db_order.id,
            old_status=old_status,
            new_status=new_status,
            changed_by_user_id=current_user.id,
            reason=reason,
        )
        
        await self.order_repo.save_order(audit_entry)
        await self.order_repo.update_order(db_order)
        
        logger.info(f"Order {order_id} status changed from {old_status} to {new_status} by user {current_user.id}")
        return True

 
    async def has_user_purchased_product(self, current_user: int, product_id: int) -> bool:
        """
        Checks if the user has a successful order containing the given product, to validate if the user can review the post
        """
        
        return await self.order_repo.exists_completed_order_for_product(
            user_id=current_user.id, product_id=product_id, status=settings.VERIFY_USER_PURCHASE
            ) # the repository returns a boolean value
