import logging
from contextlib import asynccontextmanager
from functools import wraps

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)


worker_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)

WorkerSession = async_sessionmaker(worker_engine, autoflush=False, expire_on_commit=False)


@asynccontextmanager
async def get_task_db_session():
    """Reusable async context manager for Celery tasks that auto-commits and auto-closes."""
    async with WorkerSession() as session:
        try:
            yield session
            await session.commit()
            logger.debug("Database transaction committed successfully.")
        except Exception as e:
            await session.rollback()
            # Proper error logging implementation
            logger.error(f"Database session error in background task: {e}")
            raise
        finally:
            logger.debug("Database session closed and returned to pool.")


def run_with_db(async_func):
    """
    Decorator that injects a fresh database session 
    into any async task function (similar to Depends(get_db)).
    """
    @wraps(async_func) # Preserves function metadata/name
    async def wrapper(*args, **kwargs):
        async with get_task_db_session() as session:
            return await async_func(session, *args, **kwargs)
    return wrapper