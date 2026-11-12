"""
Central database models export module.

Importing all models here guarantees that SQLAlchemy registers every mapper 
and relationship target into Base.metadata before Alembic migrations run 
or the FastAPI app boots up.
"""

from .base import Base

# 3. Shopping Cart
from .cart import Cart, CartItem

# 2. Categories & Products
from .category import Category

# 4. Orders & Payments
from .order import Order, OrderItem, OrderStatus, OrderStatusAudit
from .payment import Payment, PaymentProvider, PaymentStatus
from .product import Product, ProductImage

# 5. Reviews & Wishlist
from .review import Review

# 1. User & Profile
from .user import Profile, User, UserRole
from .wishlist import Wishlist, WishlistItem

__all__ = [
    "Base",
    "Cart",
    "CartItem",
    "Category",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderStatusAudit",
    "Payment",
    "PaymentProvider",
    "PaymentStatus",
    "Product",
    "ProductImage",
    "Profile",
    "Review",
    "User",
    "UserRole",
    "Wishlist",
    "WishlistItem",
    
]



