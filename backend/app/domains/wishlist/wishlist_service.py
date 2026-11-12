import logging

from app.core import exceptions
from app.domains.product.product_service import ProductService
from app.models import User, Wishlist, WishlistItem

from .wishlist_repository import WishlistRepository

"""Will implement for guest users too"""

logger = logging.getLogger(__name__)

class WishlistService:
    def __init__(self, wish_repo: WishlistRepository, product_service: ProductService=None):
        self.wish_repo = wish_repo
        self.product_service = product_service
    
    # This is a helper function which get the wishlist or 
    # create a new one if no existing was found
    async def _get_or_create_wishlist(self, current_user: User) -> Wishlist:
        """Helper to ensure a user always has a Wishlist container."""
        wishlist = await self.wish_repo.get_user_wishlist(user_id=current_user.id)
        if not wishlist:
            wishlist = Wishlist(user_id=current_user.id)
            wishlist = await self.wish_repo.save_wishlist_or_wishlist_item(wishlist)
        return wishlist

    """Will configure the pagination here"""
    async def get_wishlist(self, current_user: User) -> Wishlist:
        """Returns user's wishlist or a fresh empty wishlist object."""
        
        return await self._get_or_create_wishlist(current_user)
    
    async def add_wishlist(self, current_user: User, product_id: int) -> bool:
            
        db_product = await self.product_service._get_product_with_id(
            product_id=product_id, current_user=current_user
            ) 
            
        # Get or create the Wishlist container cleanly 
        wishlist = await self._get_or_create_wishlist(current_user)

        # Check for duplicates (Running for both new and existing wishlists)
        existing = await self.wish_repo.get_wishlist_item(
            wishlist_id=wishlist.id, product_id=db_product.id
            )
        if existing:
            raise exceptions.ConflictingError("Product already in wishlist")
        
        item = WishlistItem(wishlist_id=wishlist.id, product_id=db_product.id)
        
        await self.wish_repo.save_wishlist_or_wishlist_item(item)
        logger.debug(f"User:{current_user.id} added product:{product_id} to wishlist")
        return True
            
    async def remove_wishlist_item(self, current_user: User, product_id: int) -> None:
        
        wishlist = await self.wish_repo.get_user_wishlist(current_user.id)
        if not wishlist:
            raise exceptions.NotFoundError("Wishlist not found")

        deleted_item = await self.wish_repo.delete_wishlist_item(
            product_id=product_id, wishlist_id=wishlist.id
            )
        if not deleted_item:
            raise exceptions.NotFoundError("Item not found in wishlist")
        logger.debug(f"User:{current_user.id} removed product:{product_id} from wishlist")
        return True
 