import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger =  logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG, # SQL Query Logging
    pool_pre_ping=True, # connection health check
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600, # Connection Expiration(close and recreate expired connection)
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

"""
As long as your production environment is configured to run at the INFO (or WARNING) log level, any log marked as DEBUG will be automatically filtered out and ignored.

Meanwhile, in your development environment, you can set your logger level to DEBUG, and you will see all those granular database commits and tracking messages right in your terminal to help you debug.

Usually, this is controlled in your environment settings (like a .env file) with a variable like LOG_LEVEL=DEBUG for local development and LOG_LEVEL=INFO for production.

"""

async def get_db() -> AsyncGenerator[AsyncSession, None]: # index 0 is what it yields while index 1 is what is sent into the generator
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
            logger.debug("Database transaction committed successfully.")
        except Exception as e:
            await session.rollback()
            # Proper error logging implementation
            logger.error(f"Database session error: {e}")
            raise
        finally:
            logger.debug("Database session closed and returned to pool.")
        
 