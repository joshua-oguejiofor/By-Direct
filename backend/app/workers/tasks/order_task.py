import asyncio
import logging

from app.core import redis_server
from app.domains.order.order_repository import OrderRepository
from app.domains.order.order_service import OrderService
from app.domains.product.product_repository import ProductRepository
from app.domains.product.product_service import ProductService
from app.workers.celery_config import celery_app
from app.workers.woker_db import run_with_db

logger = logging.getLogger(__name__)



@run_with_db
async def clean_up_and_release_stock(session):
    """ For each loop per asyncio.run a new redis pool is open"""
    await redis_server.redis_manager.init_pool()
    try:
        product_repo = ProductRepository(session)
        product_service = ProductService(product_repo)    
        order_repo = OrderRepository(session)
        order_service = OrderService(order_repo=order_repo, product_service=product_service)
        return await order_service._release_expired_orders()
    finally:
        # close the pool after a complete run
        await redis_server.redis_manager.close_pool()



@celery_app.task(
    name="order_tasks.cleanup_expired_orders",
    autoretry_for=(Exception,), retry_backoff=True, 
    retry_jitter=True, max_retries=3             
      )
def cleanup_expired_orders():
    """
    Periodic Celery task entry point. Wraps the async SQLAlchemy worker 
    within the synchronous Celery execution loop.
    """
    try:
        logger.info("Attempting cleanup expired orders")
        
        # Run async worker inside Celery's event loop
        asyncio.run(clean_up_and_release_stock())
        logger.info("Completed order cleanup")

    except Exception as exc:
        logger.error(f"Error executing cleanup_expired_orders task: {exc}") 
        raise 


