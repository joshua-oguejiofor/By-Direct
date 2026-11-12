from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import settings

from .base_email import BaseEmail


class UserEmail(BaseEmail):
    
    def __init__(self):
        super().__init__()
        
    
    async def verify_email(self, to_email: str, exp: str, token: str) -> bool:
        
        url = f"{settings.FRONTEND_URL}/api/v1/auth/verify-email?token={token}"

        html_body = self._render_template(
            
            template_name="user/verify_email.html",
            context={"expire": exp, "verify_link": url})

        return await self.send_email(to_email, "Verify Your Email", html_body)


    async def send_otp_email(self, to_email: str, otp: str, exp: int) -> bool:
        html_body = self._render_template(
            template_name="user/otp_email.html",
            context={"otp": otp, "expire": exp}
        )
        return await self.send_email(to_email, "Your OTP Code", html_body)


    async def send_login_notification(self, to_email: str, first_name: str) -> bool:
        html_body = self._render_template(
            template_name="user/login_notification.html",
            context={"first_name": first_name, "time": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")}
        )
        return await self.send_email(to_email, "Login Notification", html_body)


    async def send_user_order_confirmation(
        self, to_email: str, 
        order_number: str, 
        total_amount: Decimal, 
        items: list
        ) -> bool:
        
        html_body = self._render_template(
            template_name="user/order_confirmation.html",
            context={"order_number": order_number, "total_amount": total_amount, "items": items}
        )
        return await self.send_email(to_email, f"Order Confirmation - {order_number}", html_body)
