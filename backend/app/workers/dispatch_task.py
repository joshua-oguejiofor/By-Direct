import logging
from decimal import Decimal

from app.workers.celery_config import celery_app

logger = logging.getLogger(__name__)


def dispatch_email_verify_token(user_email: str, token: str, exp: int, user_id: int) -> None:
    
    try:
        celery_app.send_task(
            "user_tasks.send_email_verify_token",
            args=[user_email, token, exp]
        )
        
    except Exception:
        logger.exception(f"Background Celery dispatch failed for user {user_id}")
            
        
def dispatch_login_notification(user_email: str, first_name: str) -> None:
    
    try:
        celery_app.send_task(
            "user_tasks.send_login_notification",
            args=[user_email, first_name]
        )
        
    except Exception:
        logger.exception("Background Celery dispatch failed for user login")
         
            
def dispatch_otp_email(user_email: str, otp: str, exp: int) -> None:
    
    try:
        celery_app.send_task(
            "user_tasks.send_otp",
            args=[user_email, otp, exp]
        )
        
    except Exception:
        logger.exception("Background Celery dispatch failed for otp")
            
        
def dispatch_order_comfirmation(
    email: str, 
    order_number: str, 
    total_amount: Decimal, 
    items: list) -> None:
    
    try:
        
        celery_app.send_task(
            "user_tasks.send_order_confirmation",
            args=[email, order_number, total_amount, items]
                )
        
    except Exception:
        logger.exception("Background Celery dispatch failed for order confirmation")
        
        