from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import OrderStatus, UserRole


class Settings(BaseSettings):
    """controls how Setting class reads and validates configuration values coming from
    .env or environment variables, and other settings sources."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    PROJECT_NAME: str = "By Direct"
    PROJECT_VERSION: str = "1.0.0"
    DEBUG: bool

    TEST_DATABASE_URL: str 
    TEST_REDIS_URL: str
    
    DATABASE_URL: str
    REDIS_URL: str

    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    
    # Cloudinary: the frontend uploads the file, the backend only signs the upload and deletes
    CLOUDINARY_URL: str = "https://res.cloudinary.com"
    CLOUDINARY_CLOUD_NAME: str 
    CLOUDINARY_API_KEY: str 
    CLOUDINARY_API_SECRET: SecretStr
    CLOUDINARY_UPLOAD_FOLDER: str = "by_direct/products"    
    ALLOW_LOCAL_IMAGES: bool = True
    
    #Token TTL
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15 * 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 5
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 10
    OTP_EXPIRE_MINUTES: int = 10 

 
    # Admin
    SUPERADMIN_EMAIL: str 
    SUPERADMIN_FIRST_NAME: str
    SUPERADMIN_LAST_NAME: str
    SUPERADMIN_PHONE: str
    SUPERADMIN_PASSWORD: SecretStr

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: SecretStr
    SMTP_TLS: bool = True
    EMAILS_FROM: str = "By Direct"

    # Payment
    STRIPE_SECRET_KEY: SecretStr
    STRIPE_WEBHOOK_SECRET: SecretStr
    PAYSTACK_SECRET_KEY: SecretStr

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    ALLOWED_HOSTS: list[str] = ["*"]

    FRONTEND_URL: str = "http://127.0.0.1:5500"
   
    
    LOW_STOCK_THRESHOLD: int = 10
    
    # --- Redis cache TTLs (seconds) -----------------------------------------
    CACHE_TTL_OVERVIEW: int =  5 * 60
    CACHE_TTL_REVENUE: int = 5 * 60
    CACHE_TTL_ORDERS: int = 5 * 60
    CACHE_TTL_TOP_PRODUCTS: int = 5 * 60
    CACHE_TTL_CUSTOMERS: int = 5 * 60
    CACHE_TTL_PAYMENTS: int = 5 * 60

    CACHE_KEY_PREFIX: str = "analytics"
    CATEGORY_CACHE_PRIFIX: str = "all_category"
    DEFAULT_TZ: str = "UTC"
    
    ADMINS: set = {UserRole.ADMIN, UserRole.SUPERADMIN}
    
    ANALYTICS_ORDER_STATUSES: set = {OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.CONFIRMED}
    VERIFY_USER_PURCHASE: set =  {OrderStatus.PROCESSING, OrderStatus.CONFIRMED, OrderStatus.DELIVERED, OrderStatus.SHIPPED}
    
    # Events that mark the order as failed/cancelled and release reserved stock
    FAILED_EVENTS: set = {"payment_intent.payment_failed", "payment_intent.canceled", "charge.failed", "charge.expired"}

    
    # "OrderStateMachine": Define allowed state transitions mapping current state to a set of valid next states
    ALLOWED_TRANSITIONS: dict = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"processing", "cancelled"},
        "processing": {"shipped", "cancelled"},
        "shipped": {"delivered"},
        "delivered": set(),  # Terminal state: cannot change once delivered
        "cancelled": set(),  # Terminal state: cannot reopen once cancelled
    }
    
    GUEST_COOKIE: str = "guest_id"
    GUEST_HEADER: str = "X-Guest-Id"
    GUEST_TTL_SECONDS: int = 7 * 24 * 60 * 60  # guest data lives 7 days since the last change
    GUEST_MAX_LINES: int = 50  # different products in one guest cart
    MAX_WISHLIST_ITEMS: int = 100



@lru_cache
def get_setting():
    return Settings()




settings = get_setting()

