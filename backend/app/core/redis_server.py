import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
from fastapi.encoders import jsonable_encoder
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError

from app.core import exceptions
from app.core.config import settings
from app.shared.utility import default, object_hook

logger = logging.getLogger(__name__)


class RedisCacheManager:
    """Manages the Redis connection pool and client."""

    def __init__(self) -> None:
        self.pool: aioredis.ConnectionPool | None = None
        self.client: aioredis.Redis | None = None

    async def init_pool(self) -> None:
        """Initialize the Redis connection pool."""
        logger.info("Initializing Redis connection pool...")

        retry_strategy = Retry(
            backoff=ExponentialBackoff(
                cap=1.0, base=0.1
                ),
            retries=3
            )

        self.pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
            socket_keepalive=True,
            health_check_interval=30,
            retry=retry_strategy,
            retry_on_timeout=True,
            retry_on_error=[ConnectionError, TimeoutError],
        )

        self.client = aioredis.Redis(connection_pool=self.pool)
        logger.info("Redis connection pool and client initialized successfully.")

    async def close_pool(self) -> None:
        """Close the Redis client and connection pool."""
        logger.info("Closing Redis client and connection pool...")

        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Redis client closed.")

        if self.pool:
            await self.pool.disconnect()
            self.pool = None
            logger.info("Redis connection pool disconnected.")


redis_manager = RedisCacheManager()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency for accessing Redis."""

    if redis_manager.client is None:
        logger.error("Attempted to access Redis dependency, but client is not initialized.")
        raise exceptions.AppException("Redis client is not initialized.")

    logger.debug("Providing Redis client dependency.")
    yield redis_manager.client


async def set_cache(key: str, value: Any, expire: int = 900) -> None:
    """Store a value in Redis with an expiration time."""

    if redis_manager.client is None:
        logger.warning("Redis client is None. Skipped setting cache for key=%s", key)
        return 
    
    # jsonable_encoder turns it into: {"id": 1, "title": "Hello", "created_at": "2026-10-12T..."}
    # jsonable_encoder serialized the model objects into a standard Python dictionary, json.dumps() takes that dictionary and serializes it into a JSON-formatted text string.
    serialized = (json.dumps(jsonable_encoder(value)))
    await redis_manager.client.set(key, ex=expire, value=serialized)
    logger.info("Successfully set cache for key=%s with expire=%s", key, expire)


async def get_analysis_cache(key: str) -> None:
  
    if redis_manager.client is None:
        logger.warning("Redis client is None. Skipped getting analysis cache for key=%s", key)
        return None

    raw = await redis_manager.client.get(key)
    
    if raw is None:
        logger.debug("Analysis cache miss for key=%s", key)
        return None
        
    try:
        data = json.loads(raw, object_hook=object_hook)
        logger.info("Successfully retrieved analysis cache for key=%s", key)
        return data
    except Exception as exc:  # noqa: BLE001 - Redis must never break analytics
        logger.warning("Redis GET failed for key=%s: %s", key, exc)

    
async def set_analysis_cache(key: str, value: Any, expire: int = 900) -> None:
    
    if redis_manager.client is None:
        logger.warning("Redis client is None. Skipped setting analysis cache for key=%s", key)
        return
    
    try:
        await redis_manager.client.set(key, value=json.dumps(value, default=default), ex=expire)
        logger.info("Successfully set analysis cache for key=%s with expire=%s", key, expire)
    except Exception as exc:  # noqa:BLE001
        logger.warning("Redis SET failed for key=%s: %s", key, exc)



async def get_cache(key: str) -> Any | None:
    """Retrieve a value from Redis."""

    if redis_manager.client is None:
        logger.warning("Redis client is None. Skipped getting cache for key=%s", key)
        return None

    data = await redis_manager.client.get(key)
    if data is None:
        logger.debug("Cache miss for key=%s", key)
        return None
    try:
        parsed_data = json.loads(data)
        logger.info("Successfully retrieved and parsed cache for key=%s", key)
        return parsed_data
    except (json.JSONDecodeError, TypeError) as e:
        print("redis error:", e)
        logger.warning("Cache decoding failed for key=%s, returning raw data: %s", key, e)
        return data

async def increment_cache(key: str, expire: int = 900) -> Any | None:
    if redis_manager.client is None:
        logger.warning("Redis client is None. Skipped incrementing cache for key=%s", key)
        return None
    
    value = await redis_manager.client.incr(key)
    
    # Set the TTL ONLY when the key is freshly created (value is 1)
    if value == 1:
        await redis_manager.client.expire(key, expire)
        logger.info("Created cache key=%s with initial value=1 and expire=%s", key, expire)
        
    return value


async def delete_cache(key: str) -> None:
    """Delete a cached value."""

    if redis_manager.client:
        await redis_manager.client.delete(key)
        logger.info("Successfully deleted cache for key=%s", key)
    else:
        logger.warning("Redis client is None. Skipped deleting cache for key=%s", key)


async def invalidate_token(token: str, expire: int=86400) -> None:
    """Blacklist a JWT token in Redis."""

    if redis_manager.client:
        await redis_manager.client.setex(f"blacklist:{token}", expire, "1")
        logger.info("Successfully blacklisted token with expire=%s", expire)
    else:
        logger.warning("Redis client is None. Skipped blacklisting token.")


async def is_token_blacklisted(token: str) -> bool:
    """Check whether a JWT token has been blacklisted."""

    if redis_manager.client is None:
        logger.warning("Redis client is None. Defaulting token blacklist check to False.")
        return False

    is_blacklisted = bool(await redis_manager.client.exists(f"blacklist:{token}"))
    logger.debug("Checked blacklist status for token: is_blacklisted=%s", is_blacklisted)
    return is_blacklisted


async def get_product_cache_version() -> int:
    """Get the current version of product caches, defaulting to 1."""
    
    if redis_manager.client is None:
        logger.warning("Redis client is uavailable for product cache version.")
        return None
    
    version = await redis_manager.client.get("product_cache_version")
    if version is None:
        return 1
    return int(version)

async def bump_product_cache_version() -> int:
    """Increment the product cache version, instantly invalidating all old keys."""
    # INCR creates the key at 1 if it doesn't exist, or increments it atomically
    return await redis_manager.client.incr("product_cache_version")