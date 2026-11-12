"""
Guest wishlist kept in Redis (no database rows for guests).

    key    guest_wishlist:{guest_id}     (Redis set of product ids)
"""
from fastapi import HTTPException

from app.core import exceptions
from app.core.config import settings
from app.core.redis_server import redis_manager
from app.domains.product.product_service import ProductService
from app.models import User
from app.shared.utility import build_cache_key


class GuestWishlistService:
    def __init__(self, product_service: ProductService):
        self.product_service = product_service

    @staticmethod
    def _key(guest_id: str) -> str:
        key = build_cache_key("guest_wishlist", f"{guest_id}")
        return key

    @staticmethod
    def _redis():
        if redis_manager.client is None:
            raise exceptions.AppException("Guest wishlist is temporarily unavailable.")
        return redis_manager.client

    async def get_wishlist(self, guest_id: str) -> dict:
        ids = sorted(int(p) for p in await self._redis().smembers(self._key(guest_id)))
        # same shape as the logged-in wishlist: {"id": ..., "items": [{"product_id": ...}]}
        return {"id": None, "items": [{"product_id": pid} for pid in ids]}

    async def add_wishlist(self, guest_id: str, product_id: int) -> bool:
        await self.product_service._get_product_with_id(product_id, current_user=None)  # must exist and be active

        r = self._redis()
        key = self._key(guest_id)
        if await r.sismember(key, str(product_id)):
            raise exceptions.ConflictingError("Product already in wishlist")
        
        if await r.scard(key) >= settings.MAX_WISHLIST_ITEMS: # Use scan to avoid interuption in redis
            raise exceptions.BadRequestError("Guest wishlist is full. Please log in to continue.")

        await r.sadd(key, str(product_id))
        await r.expire(key, settings.GUEST_TTL_SECONDS)
        return True

    async def remove_wishlist_item(self, guest_id: str, product_id: int) -> bool:
        if not await self._redis().srem(self._key(guest_id), str(product_id)):
            raise exceptions.NotFoundError("Item not found in wishlist")
        return True

    async def merge_into_user(self, guest_id: str, user: User, wishlist_service) -> dict:
        r = self._redis()
        key = self._key(guest_id)
        merged = skipped = 0

        for pid_text in await r.smembers(key):
            try:
                await wishlist_service.add_wishlist(user, int(pid_text))
                merged += 1
            except (exceptions.AppException, HTTPException):  # already there / product gone
                skipped += 1

        await r.delete(key)
        return {"merged": merged, "skipped": skipped}
