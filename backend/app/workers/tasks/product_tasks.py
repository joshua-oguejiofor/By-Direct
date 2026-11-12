import asyncio
import logging

from app.domains.analytics import analitics_repository, analytics_service
from app.email_server.product_email import ProductEmail
from app.workers.celery_config import celery_app
from app.workers.woker_db import run_with_db

user_mail = ProductEmail()

logger = logging.getLogger(__name__)



# Tested to be working
@run_with_db
async def _run_low_stock_check(session, quantity: int):
    """
    Helper async function to handle email logic cleanly. Using the reusable session manager with @run_with_db decorator"""
    analytics_repo = analitics_repository.AnalyticsRepository(session)
    analytics_serv = analytics_service.AnaliticsService(analytics_repo)
    result = await analytics_serv.get_low_inventory_products(quantity=quantity, page_size=100)
    
    low_product = result["products"]

    if low_product:
        
        await user_mail.low_stock_alart(low_product_object=low_product)



@celery_app.task(
    name="product_tasks.send_low_stock_alert",
    autoretry_for=(Exception,), retry_backoff=True, 
    retry_jitter=True, max_retries=3
    )
def send_low_stock_alert_task(quantity: int = 10):
    
        try: # Run the entire async workflow in one asyncio loop
            logger.info("Attempting to send low stock alert")
            
            asyncio.run(_run_low_stock_check(quantity=quantity))
            
            logger.info("Successfully sent low stock alert")
        except Exception as exc:  
            logger.error(f"Failed to send low stock alert email. Error: {exc}")  
            raise 

