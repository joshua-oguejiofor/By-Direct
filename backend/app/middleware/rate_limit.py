import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=["100/minutes"]
)


def set_rate_limit(app: FastAPI):
    app.state.limiter = limiter
    app.add_middleware(SlowAPIASGIMiddleware)
    @app.exception_handler(RateLimitExceeded) 
    async def rate_limit_exception(request: Request, exc: RateLimitExceeded):
        # Log a warning when a client exceeds their rate limit
        logger.warning(f"Rate limit hit for client IP: {request.client.host}")
        return JSONResponse(
            status_code=429,
            content={
                "error": True,
                "msg":"Too many request, try again after sometime."
            }
            
        )