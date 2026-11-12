import asyncio
import logging
from decimal import Decimal

from app.email_server.user import UserEmail
from app.workers.celery_config import celery_app

logger = logging.getLogger(__name__)

user_mail = UserEmail()



@celery_app.task(
    name="user_tasks.send_email_verify_token",   # Provide an explicit task name
    autoretry_for=(Exception,),  # Automatically retry on any unexpected exception
    retry_backoff=True, # Enable exponential backoff(gradually increase the delay time before retry)
    retry_jitter=True, # Add jitter to prevent thundering herd problem(prevent multiple retires at onced)
    max_retries=3,  # Cap the max retries so it doesn't loop forever
    )
def email_verify_token_task(to_email: str, token: str, exp):
    try:
        logger.info(f"Attempting to send verification email to {to_email}")
        
        asyncio.run(
            user_mail.verify_email(
            to_email=to_email, exp=exp, 
            token=token))
        logger.info(f"Successfully sent verification email to {to_email}")

    except Exception as exc: 
        logger.error(f"Failed to send verification email to {to_email}. Error: {exc}")
        raise


@celery_app.task(
    name="user_tasks.send_otp", 
    autoretry_for=(Exception,), retry_backoff=True, 
    retry_jitter=True, max_retries=3
    )    
def send_otp_email_task(to_email: str, otp: str, exp: int):
    try:
        logger.info(f"Attempting to send OTP to {to_email}")
        
        asyncio.run(
            user_mail.send_otp_email(
            to_email=to_email, otp=otp, exp=exp))
        logger.info(f"Successfully sent OTP to {to_email}")
        
    except Exception as exc: 
        logger.error(f"Failed to send OTP to {to_email}. Error: {exc}")
        raise
    
    
@celery_app.task(
    name="user_tasks.send_login_notification",
    autoretry_for=(Exception,), retry_backoff=True, 
    retry_jitter=True, max_retries=3
        )
def send_login_notification_task(to_email: str, first_name: str):
    try:
        logger.info(f"Attempting to send login notification to {to_email}")
        
        asyncio.run(
            user_mail.send_login_notification(
            to_email=to_email,
            first_name=first_name))
        logger.info(f"Successfully sent login notification to {to_email}")
        
    except Exception as exc: 
        logger.error(f"Failed to send login notification to {to_email}. Error: {exc}")
        raise 


@celery_app.task(
    name="user_tasks.send_order_confirmation",
    autoretry_for=(Exception,), retry_backoff=True, 
    retry_jitter=True, max_retries=3
        )
def send_order_confirmation_task(
    to_email: str, order_number: str, 
    total_amount: Decimal, items: list
    ):
    try:
        logger.info(f"Attempting to send order confirmation email to {to_email}")
        
        asyncio.run(
            user_mail.send_user_order_confirmation(
            to_email=to_email, order_number=order_number, 
            total_amount=total_amount, items=items)
                    )
        logger.info(f"Successfully sent order confirmation to {to_email}")
        
    except Exception as exc:  
        logger.error(f"Failed to send order confirmation to {to_email}. Error: {exc}")
        raise 


