from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Cart, CartItem


class CartRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def check_user_cart(self, user_id: int) -> bool:
        result = await self.db.execute(
            select(
                exists()
                .where(Cart.user_id == user_id))
        )
        return bool(result.scalar())
    
    async def get_user_cart(self, user_id: int) -> Cart | None:
        result = await self.db.execute(
            select(Cart)
            .options(selectinload(Cart.items))
            .where(Cart.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    
    async def get_cart_item(self, cart_id: int, product_id: int):
        result = await self.db.execute(
            select(CartItem)
            .where(
                CartItem.cart_id == cart_id, 
                CartItem.product_id == product_id
                )
        )
        return result.scalar_one_or_none()
    
    async def add_cart_or_cart_item(self, obj: Cart | CartItem) -> Cart | CartItem:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
        
    async def update_cart_or_cart_item(self, obj: Cart | CartItem) -> Cart | CartItem:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj


    async def delete_item(self, cart_id: int, item_id: int) -> bool:
        result = await self.db.execute(
            delete(CartItem)
            .where(
                CartItem.id == item_id,
                CartItem.cart_id == cart_id
            )
        )
        await self.db.flush()
        return result.rowcount > 0

    async def clear_cart_items(self, cart_id: int) -> None:
        await self.db.execute(
            delete(CartItem).where(CartItem.cart_id == cart_id)
        )
        await self.db.flush()