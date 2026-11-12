from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Wishlist, WishlistItem


class WishlistRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    
    async def get_user_wishlist(self, user_id: int) -> Wishlist | None:
        
        result = await self.db.execute(
            select(Wishlist)
            .options(selectinload(Wishlist.items))
            .where(Wishlist.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    
    async def get_wishlist_item(self, wishlist_id: int, product_id: int) -> WishlistItem | None:
        result = await self.db.execute(
            select(WishlistItem)
            .where(
                WishlistItem.wishlist_id == wishlist_id, WishlistItem.product_id == product_id
                )
        )
        return result.scalar_one_or_none()
    
    
    async def save_wishlist_or_wishlist_item(self, obj: Wishlist | WishlistItem) -> Wishlist:
            self.db.add(obj)
            await self.db.flush()
            await self.db.refresh(obj)
            return obj
    
    """the delete() statement itself knows how many rows were affected.

        You can use result.rowcount to determin if the query was successfull"""
    async def delete_wishlist_item(self, product_id: int, wishlist_id: int) -> bool:
        result = await self.db.execute(
            delete(WishlistItem)
            .where(
                WishlistItem.product_id == product_id, 
                WishlistItem.wishlist_id == wishlist_id
                )
        )
        await self.db.flush()
        return result.rowcount > 0