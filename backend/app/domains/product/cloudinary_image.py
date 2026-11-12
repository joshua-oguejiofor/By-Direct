"""
Cloudinary helper. The FRONTEND uploads the file straight to Cloudinary.
The backend only:
  1. signs the upload (so only logged-in admins can upload), and
  2. deletes images when a product / image is removed.
The Cloudinary SDK is synchronous, so every call runs in a thread (asyncio.to_thread).
"""
import asyncio
import logging
import time

import cloudinary
import cloudinary.api
import cloudinary.utils

from app.core.config import settings

logger = logging.getLogger(__name__)


def _configure() -> None:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET.get_secret_value(),
        secure=True,
    )


def sign_upload() -> dict:
    """Parameters the frontend must send to Cloudinary (the secret never leaves the server)."""
    _configure()
    params = {"timestamp": int(time.time()), "folder": settings.CLOUDINARY_UPLOAD_FOLDER}
    signature = cloudinary.utils.api_sign_request(params, settings.CLOUDINARY_API_SECRET.get_secret_value())
    return {
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
        "api_key": settings.CLOUDINARY_API_KEY,
        "timestamp": params["timestamp"],
        "folder": params["folder"],
        "signature": signature,
    }


def _delete_sync(public_ids: list[str]) -> dict:
    _configure()
    # up to 100 ids per call; invalidate=True also clears the CDN copy
    return cloudinary.api.delete_resources(public_ids, resource_type="image", invalidate=True)



async def delete_images(public_ids: list[str]) -> None:
    """Runs AFTER the response (BackgroundTasks). Never raises: a failed cloud delete must not break the API."""
    ids = [p for p in public_ids if p]
    if not ids:
        return
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            result = await asyncio.to_thread(_delete_sync, chunk)
            logger.info(f"Cloudinary delete {chunk} -> {result.get("deleted")}")
        except Exception:
            logger.exception(f"Cloudinary delete FAILED for {chunk} (orphaned images, clean up manually)")
