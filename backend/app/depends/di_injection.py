from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.analytics import analitics_repository, analytics_service
from app.domains.auth import auth_repository, auth_service
from app.domains.cart import cart_repository, cart_service
from app.domains.cart.guest_cart_service import GuestCartService
from app.domains.category import category_repository, category_service
from app.domains.order import order_repository, order_service
from app.domains.payment import payment_repository, payment_service
from app.domains.product import product_repository, product_service
from app.domains.review import review_repository, review_service
from app.domains.user import user_repository, user_service
from app.domains.webhook.webhook_service import WebookEventService
from app.domains.wishlist import wishlist_repository, wishlist_service
from app.domains.wishlist.guest_wishlist_service import GuestWishlistService

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]




def get_auth_service(db: DBSessionDep):
    auth_repo = auth_repository.AuthRepository(db)
    return auth_service.AuthService(auth_repo)

def get_cart_service(db: DBSessionDep):
    cart_repo = cart_repository.CartRepository(db)
    product_serv = get_product_service(db)
    return cart_service.CartService(cart_repo=cart_repo, product_service=product_serv)

def get_product_service(db: DBSessionDep):
    category_service = get_category_service(db)
    product_repo = product_repository.ProductRepository(db)
    return product_service.ProductService(product_repo=product_repo, category_service=category_service)
    
def get_category_service(db: DBSessionDep):
    category_repo = category_repository.CategoryRepository(db)
    return category_service.CategoryService(category_repo)

def get_user_service(db: DBSessionDep):
    user_repo = user_repository.UserRepository(db)
    return user_service.UserService(user_repo)

def get_review_service(db: DBSessionDep):
    order_service = get_order_service(db)
    review_repo = review_repository.ReviewRepository(db)
    product_service = get_product_service(db)
    return review_service.ReviewService(review_repo=review_repo, order_service=order_service, product_service=product_service)

def get_order_service(db: DBSessionDep):
    order_repo = order_repository.OrderRepository(db)
    product_service = get_product_service(db)
    cart_service = get_cart_service(db)
    payment_service = get_payment_service(db)
    user_service = get_user_service(db)
    return order_service.OrderService(
        order_repo=order_repo, product_service=product_service, 
        cart_service=cart_service, payment_service=payment_service,
        user_service=user_service
        )

def get_wishlist_service(db: DBSessionDep):
    wish_repo = wishlist_repository.WishlistRepository(db)
    product_service = get_product_service(db)
    return wishlist_service.WishlistService(wish_repo=wish_repo, product_service=product_service)

def get_payment_service(db: DBSessionDep):
    payment_repo = payment_repository.PaymentRepository(db)
    return payment_service.PaymentService(payment_repo)

def get_webhook_service(db: DBSessionDep):
    order_service = get_order_service(db)
    payment_service = get_payment_service(db)
    return WebookEventService(order_service=order_service, payment_service=payment_service)

def get_analytics_service(db: DBSessionDep) -> analytics_service.AnaliticsService:
    analytics_repo = analitics_repository.AnalyticsRepository(db)
    return analytics_service.AnaliticsService(analytics_repo)


def get_guest_cart_service(db: DBSessionDep) -> GuestCartService:
    return GuestCartService(get_product_service(db))


def get_guest_wishlist_service(db: DBSessionDep) -> GuestWishlistService:
    return GuestWishlistService(get_product_service(db))
