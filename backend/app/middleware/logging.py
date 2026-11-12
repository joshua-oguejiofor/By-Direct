import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs information about every HTTP request.

    For each request, it:
    1. Records the start time.
    2. Passes the request to the FastAPI application.
    3. Waits for the endpoint to return a response.
    4. Calculates how long the request took.
    5. Logs the HTTP method, URL path, status code, and duration.

    Example log:
        POST /api/v1/orders status=201 duration=0.245s
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process a request and log details about the resulting response.

        `call_next` passes the request to the next middleware or
        FastAPI route handler. The response is returned after the
        request has been processed.
        """
        start = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start

        logger.info(
            "%s %s status=%s duration=%.3fs",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )

        return response