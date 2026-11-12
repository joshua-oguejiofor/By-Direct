import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core import config, exceptions, redis_server, reg_admin
from app.domains.analytics.analitics_route import router as analytics_router
from app.domains.auth.auth_route import router as auth_router
from app.domains.cart.cart_route import router as cart_router
from app.domains.category.category_route import router as category_router
from app.domains.order.order_route import router as order_router
from app.domains.payment.payment_route import router as payment_router
from app.domains.product.product_route import router as product_router
from app.domains.review.review_route import router as review_router
from app.domains.user.user_route import router as user_router
from app.domains.webhook.webhook_route import router as webhook_router
from app.domains.wishlist.wishlist_route import router as wishlist_router
from app.middleware import logging as app_log
from app.middleware import rate_limit

logging.basicConfig(
    level=logging.INFO,
    format = "%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

    
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""

    logger.info("Starting By-Direct")
    await reg_admin.register_superadmin_user()
    
    # Startup redis
    await redis_server.redis_manager.init_pool()
    try:
        yield
    finally:
        # Shutdown redis
        await redis_server.redis_manager.close_pool()
    logger.info("Stopping By-Direct")


app = FastAPI(
    title=config.settings.PROJECT_NAME,
    version=config.settings.PROJECT_VERSION,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redocs",
    lifespan=lifespan,
)

rate_limit.set_rate_limit(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Guest-Id"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.settings.ALLOWED_HOSTS,)
app.add_middleware(app_log.LoggingMiddleware)


app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentications"])
app.include_router(cart_router, prefix="/api/v1/carts", tags=["Cart"])
app.include_router(category_router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(order_router, prefix="/api/v1/orders", tags=["Orders"])
app.include_router(product_router, prefix="/api/v1/products", tags=["Products"])
app.include_router(payment_router, prefix="/api/v1", tags=["Payments"])
app.include_router(review_router, prefix="/api/v1/reviews", tags=["Reviews"])
app.include_router(user_router, prefix="/api/v1/users", tags=["Users"])
app.include_router(wishlist_router, prefix="/api/v1/wishlists", tags=["Wishlist"])
app.include_router(analytics_router, prefix="/api/v1/admin/analytics", tags=["Analytics"])
app.include_router(webhook_router, prefix="/api/v1/webhooks", tags=["Webhook"])



#Error handlers
exceptions.register_exception_handlers(app)


@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    return {
    "status": "Healthy", 
    "version": config.settings.PROJECT_VERSION, 
    "service": config.settings.PROJECT_NAME
    }
    
    
    
    
 