
"""
I will convert this cart to used redis hash
"""

import logging
from decimal import Decimal

from app.core import exceptions
from app.domains.product.product_service import ProductService
from app.models import Cart, CartItem, User
from app.shared.utility import optimize_prize

from .cart_repository import CartRepository
from .cart_schema import CartItemAdd

logger = logging.getLogger(__name__)

class CartService:
    def __init__(self, cart_repo: CartRepository, product_service: ProductService = None):
        self.cart_repo = cart_repo
        self.product_service = product_service


    async def _get_cart(self, user_id: int) -> Cart:
        
        if not await self.cart_repo.check_user_cart(user_id):
            cart = Cart(user_id=user_id)
            await self.cart_repo.add_cart_or_cart_item(cart)
            
        return await self.cart_repo.get_user_cart(user_id)
    
    
    async def get_cart_with_items(self, user_id: int) -> dict:
        
 
        db_cart = await self._get_cart(user_id)
        
                
        if not db_cart.items:
            return {
                "id": db_cart.id, "items": [], 
                "total_items": 0, "total_amount": Decimal("0.00")
                }
            
                    
        items = []
        total = Decimal("0.00")
        total_items = 0
        for item in db_cart.items:
            try:
                product = await self.product_service._get_product_with_id(item.product_id, current_user=None)
            except exceptions.NotFoundError: # If product was deleted or deactivated it wount break the loop
                continue
            
            price = optimize_prize(product)
            line_total = price * item.quantity
            total += line_total
            total_items += item.quantity
            items.append({
                "id": item.id,  
                "product_id": item.product_id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": price,
                "total_price": line_total,
                "in_stock": product.stock_quantity >= item.quantity,
            })

        return {
            "id": db_cart.id, "items": items, 
            "total_items": total_items, "total_amount": total
            }
                

    async def add_item(self, current_user: User, data: CartItemAdd) -> dict[str, str]:
        
        db_product = await self.product_service._get_product_with_id(product_id=data.product_id, current_user=current_user)
        
        if db_product.stock_quantity < data.quantity:
            raise exceptions.BadRequestError("Insufficient stock")
        
        if db_product.is_active == False:
            raise exceptions.BadRequestError(f"Product {db_product.name} is not available for sale.")

        cart = await self._get_cart(current_user.id)
        
        existing_item = await self.cart_repo.get_cart_item(cart_id=cart.id, product_id=data.product_id)

        if existing_item:
            new_quantity = existing_item.quantity + data.quantity
            if db_product.stock_quantity < new_quantity:  # check BEFORE changing the row
                raise exceptions.BadRequestError("Exceeds available stock")
            
            existing_item.quantity += data.quantity
            await self.cart_repo.update_cart_or_cart_item(existing_item)
            
        else:
            price = db_product.discount_price if db_product.discount_price is not None else db_product.price
            item = CartItem(
                cart_id=cart.id,
                product_id=data.product_id,
                quantity=data.quantity,
                unit_price=price,
            )
            
            await self.cart_repo.add_cart_or_cart_item(item)
            
        logger.debug(f"User:{current_user.id} added product:{data.product_id} to cart")
        return {"msg": "Item added to cart"}


    async def remove_item(self, current_user: User, item_id: int) -> bool:
        cart = await self._get_cart(current_user.id)
        deleted = await self.cart_repo.delete_item(cart_id=cart.id, item_id=item_id)
        
        if not deleted:
            raise exceptions.NotFoundError("Cart item not found")
        logger.debug(f"User:{current_user.id} removed product:{item_id} to cart")
        return True
    
    async def clear_cart(self, user_id: int) -> bool:
        cart = await self._get_cart(user_id)            
        await self.cart_repo.clear_cart_items(cart.id)
        
        return True