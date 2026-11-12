"""
Guest cart kept in Redis (no database rows for guests).
    storage = (Redis hash)
    key =   guest_cart:{guest_id} 
    field = product_id
    value = quantity

Only ids and quantities are stored. Names and prices are read from the database
every time, so a guest can never keep an old price.
"""
from decimal import Decimal

from fastapi import HTTPException

from app.core import exceptions
from app.core.config import settings
from app.core.redis_server import redis_manager
from app.domains.product.product_service import ProductService
from app.models import User
from app.shared.utility import build_cache_key, optimize_prize

from .cart_schema import CartItemAdd


class GuestCartService:
    def __init__(self, product_service: ProductService):
        self.product_service = product_service

    @staticmethod
    def guest_key(guest_id: str) -> str:
        """Following DRY, this will be set once. Using '@staticmethod' to bind it to this class """
        key = build_cache_key("guest_cart", f"{guest_id}")
        return key

    @staticmethod
    def _redis():
        if redis_manager.client is None:
            raise exceptions.AppException("Guest cart is temporarily unavailable.")
        return redis_manager.client

    async def get_cart_with_items(self, guest_id: str) -> dict:
        r = self._redis()
        key = self.guest_key(guest_id)
        items = []
        total = Decimal("0.00")
        total_items = 0

        for pid_text, qty_text in (await r.hgetall(key)).items():
            product_id, quantity = int(pid_text), int(qty_text)
            try:
                product = await self.product_service._get_product_with_id(product_id, current_user=None)
            except exceptions.NotFoundError:
                await r.hdel(key, pid_text)  # If product was deleted or deactivated it wount break the loop
                continue

            price = optimize_prize(product)
            line_total = price * quantity
            total += line_total
            total_items += quantity
            items.append({
                "id": product_id,  # for guests the item id IS the product id
                "product_id": product_id,
                "product_name": product.name,
                "quantity": quantity,
                "unit_price": price,
                "total_price": line_total,
                "in_stock": product.stock_quantity >= quantity,
            })

        return {"id": None, "items": items, "total_items": total_items, "total_amount": total}

    async def add_item(self, guest_id: str, data: CartItemAdd) -> dict[str, str]:
        product = await self.product_service._get_product_with_id(data.product_id, current_user=None)

        r = self._redis()
        key = self.guest_key(guest_id)
        field = str(data.product_id)

        current = int(await r.hget(key, field) or 0)
        new_quantity = current + data.quantity
        if new_quantity > product.stock_quantity:
            raise exceptions.BadRequestError("Exceeds available stock")
        
        if current == 0 and await r.hlen(key) >= settings.GUEST_MAX_LINES:
            raise exceptions.BadRequestError("Guest cart is full. Please log in to continue.")

        await r.hset(key, field, new_quantity)
        await r.expire(key, settings.GUEST_TTL_SECONDS)
        return {"msg":"Item added to cart"}

    async def remove_item(self, guest_id: str, product_id: int) -> bool:
        removed = await self._redis().hdel(self.guest_key(guest_id), str(product_id))
        if not removed:
            raise exceptions.NotFoundError("Cart item not found")
        return True


    async def clear_cart(self, guest_id: str) -> bool:
        await self._redis().delete(self.guest_key(guest_id))
        return True

    async def merge_into_user(self, guest_id: str, user: User, cart_service) -> dict:
        """Copy the guest cart into the user's database cart, then delete it.
        A line that cannot be added (out of stock, product gone) is skipped."""
        r = self._redis()
        key = self.guest_key(guest_id)
        merged = skipped = 0

        for pid_text, qty_text in (await r.hgetall(key)).items():
            try:
                await cart_service.add_item(
                    user, CartItemAdd(product_id=int(pid_text), quantity=int(qty_text))
                )
                merged += 1
            except (exceptions.AppException, HTTPException):
                skipped += 1

        await r.delete(key)
        return {"merged": merged, "skipped": skipped}
