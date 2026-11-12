import asyncio
import logging
from datetime import UTC, datetime

from app.core import redis_server
from app.core.enums import Period
from app.depends.analitics_depends import resolve_period
from app.domains.analytics.analitics_repository import AnalyticsRepository
from app.domains.analytics.analytics_service import AnaliticsService
from app.email_server.analytics_email import AnalyticsEmail
from app.workers.celery_config import celery_app
from app.workers.woker_db import run_with_db

analytics_email = AnalyticsEmail()

logger = logging.getLogger(__name__)

@run_with_db
async def _montly_analitics_report(session):
    await redis_server.redis_manager.init_pool()
    try:
        repo = AnalyticsRepository(session)
        service = AnaliticsService(repo)    
        
        resolve_range = resolve_period(period=Period.PREVIOUS_MONTH, start_date=None, end_date=None, now=datetime.now(UTC))
        overview = await service.get_overview(resolve_range)
        growth = await service.get_period_comparison(resolve_range)
        await analytics_email.montly_analysis_report (overview=overview, growth=growth)
    finally:
            # close the pool after a complete run
            await redis_server.redis_manager.close_pool()
    
    

@celery_app.task(
    name="analytics_tasks.monthly_analytics_report",
    autoretry_for=(Exception,), retry_backoff=True, 
    retry_jitter=True, max_retries=3             
          )
def monthly_analytics_report():
    try:
        logger.info("Attempting to send montly report")
        
        asyncio.run(_montly_analitics_report())
        logger.info("Successfully sent montly report")
        
    except Exception as exc:
        logger.error(f"Failed to send montly analytics report. Error:{exc}")
        raise 

