import logging
import secrets
import time

from fastapi import BackgroundTasks, Request
from fastapi.responses import RedirectResponse

from app.core import exceptions, redis_server, security
from app.core.config import settings
from app.models.user import User
from app.shared.utility import build_cache_key, get_frontend_redirect_url
from app.workers.dispatch_task import (
    dispatch_email_verify_token,
    dispatch_login_notification,
    dispatch_otp_email,
)

from .auth_repository import AuthRepository
from .auth_schema import CreateUser, TokenResponse

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, auth_repo: AuthRepository):
        self.auth_repo = auth_repo
    
    @staticmethod
    def _get_jti() -> str:
        return str(secrets.token_urlsafe(32))
    
    
    @staticmethod
    def _get_refresh_key(user_id):
        return f"refresh_token_jti:{user_id}"

    async def register(self, data: CreateUser, background_tasks: BackgroundTasks) -> bool:

        if await self.auth_repo.check_email_exist(data.email):
            logger.warning("Duplicate email attempt")
            raise exceptions.BadRequestError("Email already registered")

        user = User(
            email=data.email,
            hashed_password=security.hash_user_password(data.password)
        )
        added_user = await self.auth_repo.save_user(user)

        email_register_jti = self._get_jti()
        
        token = security.create_email_verification_token({"sub":  str(added_user.id), "jti": email_register_jti})
        exp = settings.EMAIL_VERIFICATION_EXPIRE_HOURS
        
        await redis_server.set_cache(
            key=f"email_verify{added_user.id}",
            value=email_register_jti,
            expire=exp * 60 * 60
        )
        
        background_tasks.add_task(dispatch_email_verify_token, user_email=added_user.email, token=token, exp=exp, user_id=added_user.id)
    
        logger.info(f"User registered successfully: {user.id}, verification email sent.")
        return True

    async def resend_email(self, email: str, background_tasks: BackgroundTasks) -> bool:

        db_user = await self.auth_repo.get_email(email)
        if not db_user:
            raise exceptions.NotFoundError("User not found")

        if db_user.is_verified:
            raise exceptions.BadRequestError("Email already verified.")

        email_register_jti = self._get_jti()
        token = security.create_email_verification_token({"sub": str(db_user.id), "jti": email_register_jti})
        exp = settings.EMAIL_VERIFICATION_EXPIRE_HOURS
        
        await redis_server.set_cache(
            key=f"email_verify{db_user.id}",
            value=email_register_jti,
            expire=exp * 60 * 60
        )
        
        background_tasks.add_task(dispatch_email_verify_token, user_email=db_user.email, token=token, exp=exp, user_id=db_user.id)
        logger.info(f"Resent verification email to: {db_user.id}")
        
        return True

    async def email_verify_token(self, token: str) -> RedirectResponse:

        try:
            payload = security.decode_token(token)
        except (exceptions.BadRequestError, exceptions.UnauthorizedError) as e:
            logger.error(f"Error occured during email verification: {e}")
            redirect_url = get_frontend_redirect_url(msg=e, prifix="/status")
            return RedirectResponse(
                url=redirect_url, status_code=302
            )

        if not payload or payload.get("type") != "verify_email":
            logger.warning(f"Invalid token type: {payload.get('type')}")
            msg = "Invalid token type"
            redirect_url = get_frontend_redirect_url(msg=msg, prifix="/status")
            return RedirectResponse(
                url=redirect_url, status_code=302
            )
        
        if await redis_server.is_token_blacklisted(payload.get("jti")):
            msg = "Session expired."
            redirect_url = get_frontend_redirect_url(msg=msg, prifix="/status")
            return RedirectResponse(
                url=redirect_url, status_code=302
            )
            
        user_id = payload.get("sub")
        db_user = await self.auth_repo.get_by_id(user_id)
        
        if not db_user:
            msg = "User not found"
            redirect_url = get_frontend_redirect_url(msg=msg, prifix="/status")
            return RedirectResponse(
                url=redirect_url, status_code=302
            )
            
        if db_user.is_verified:
            msg = "User already verified"
            redirect_url = get_frontend_redirect_url(msg=msg, prifix="/status")
            return RedirectResponse(
                url=redirect_url, status_code=302
            )

        remaining_time = max(payload.get("exp") - int(time.time()), 1)

        db_user.is_verified = True

        await self.auth_repo.update_user(db_user)
        await redis_server.invalidate_token(payload.get("jti"), remaining_time)
        logger.info(f"Email verifification successful for user {db_user.id}")
        
        msg = "Email verified successfully"
        redirect_url = get_frontend_redirect_url(msg=msg, prifix="/status")
        return RedirectResponse(
            url=redirect_url, status_code=302
        )


    async def login(self, email: str, password: str, background_tasks: BackgroundTasks, request: Request) -> TokenResponse:
        
        ip_address = str(request.client.host if request.client else "unknown")
        cache_key = build_cache_key("lock", email, ip_address)
        lock_key = build_cache_key(cache_key, "locked")
        
        if await redis_server.get_cache(lock_key):
            logger.warning(f"Login attempts for email {email} exceeded limit. Account locked.")
            raise exceptions.ForbiddenError("Account locked due to multiple failed login attempts. Please try again after time.")

        user = await self.auth_repo.login_user(email)

        if not user or not security.verify_user_password(password, user.hashed_password):
            logger.warning(f"Failed login attempts for: {email} on {ip_address} address")

            attempts = await redis_server.increment_cache(cache_key)  # Autommically delete after 15 minutes
            
            if attempts >= 5:
                await redis_server.set_cache(key=lock_key, value="blocked", expire=900)

            raise exceptions.UnauthorizedError("Invalid credentials")

        if user.is_active == False:
            raise exceptions.UnauthorizedError("Invalid credentials")

        if not user.is_verified:
            raise exceptions.UnauthorizedError("Please verify your email before logging in.")
        
        # Clear the failed login attempts counter upon successful authentication
        await redis_server.delete_cache(cache_key)
        
        refresh_key = self._get_refresh_key(user.id)
        refresh_jti = self._get_jti()
         
        access_token = security.create_access_token({"sub": str(user.id), "role": user.role, "jti": self._get_jti()})
        refresh_token = security.create_refresh_token({"sub": str(user.id), "role": user.role, "jti": refresh_jti})

        await redis_server.set_cache(
            key=refresh_key,
            value=refresh_jti,
            expire=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)

        first_name = user.profile.first_name if user.profile else user.email.split("@")[0]
        background_tasks.add_task(dispatch_login_notification, user_email=user.email, first_name=first_name)
        logger.info(f"Successful login for user: {user.id}")
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

        
    async def refresh_token(self, refresh_token: str) -> TokenResponse:
                    
        payload = security.decode_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            raise exceptions.UnauthorizedError("Invalid token type")
        
        old_jti = payload.get("jti")
        
        if await redis_server.is_token_blacklisted(old_jti):
            raise exceptions.BadRequestError("Invalid or expired refresh token")
        
        user_id = payload.get("sub")
        
        if not await self.auth_repo.validate_user_refr_token(int(user_id)):
            raise exceptions.UnauthorizedError("Unauthorized access.")
        
        new_jti = self._get_jti()
        refresh_key = self._get_refresh_key(user_id)
        
        new_access_token = security.create_access_token({"sub": str(user_id), "role": payload.get("role"), "jti": self._get_jti()})
        new_refresh_token = security.create_refresh_token({"sub": str(user_id), "role": payload.get("role"), "jti": new_jti})

        await redis_server.set_cache(
            key=refresh_key,
            value=new_jti,
            expire=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            )
        
        remaining_time = max(payload.get("exp") - int(time.time()), 1)

        # Blacklist refresh token
        await redis_server.invalidate_token(old_jti, remaining_time)
        return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)


    async def change_password(self, old_password: str, new_password: str, user: User) -> bool:

        user = await self.auth_repo.get_by_id(user.id)
        if not user:
            raise exceptions.NotFoundError("User not found")

        if not security.verify_user_password(old_password, user.hashed_password):
            raise exceptions.BadRequestError("Old password is invalid")

        user.hashed_password = security.hash_user_password(new_password)
        await self.auth_repo.update_user(user)
        logger.info(f"Password changed successfully for user {user.id}")
        return True

    async def forget_password(self, email: str, background_task: BackgroundTasks) -> bool:

        user = await self.auth_repo.get_email(email)
        if not user:
            logger.warning(f"Invalid email address for forget password {email}")
            return True

        otp = security.generate_otp()
        
        exp = settings.OTP_EXPIRE_MINUTES
        await redis_server.set_cache(key=f"otp:{email}", value=otp, expire=exp * 60)
        
        background_task.add_task(dispatch_otp_email, user_email=user.email, otp=otp, exp=exp)
        return True

    async def verify_otp(self, email: str, otp: str) -> dict[str, str]:

        cache_key = f"otp:{email}"
        stored_otp = await redis_server.get_cache(cache_key)
        if not stored_otp or stored_otp != otp:
            raise exceptions.UnauthorizedError("Invalid OTP")

        reset_token = security.password_reset_token({"sub": email, "jti": self._get_jti()})
        await redis_server.delete_cache(cache_key)
        
        return {"reset_token": reset_token}


    async def reset_password(self, reset_token: str, new_password: str) -> bool:

        payload = security.decode_token(reset_token)
        
        if not payload or payload.get("type") != "password_reset":
            raise exceptions.BadRequestError("Invalid token type")
        
        token_jti = payload.get("jti")
        
        if await redis_server.is_token_blacklisted(token_jti):
            raise exceptions.UnauthorizedError("Expired reset token")
                
        email = payload.get("sub")

        db_user = await self.auth_repo.get_email(email)
        if not db_user:
            raise exceptions.NotFoundError("Unable to reset password for this account")
        
        db_user.hashed_password = security.hash_user_password(new_password)

        remaining_time = max(payload.get("exp") - int(time.time()), 1)

        await self.auth_repo.update_user(db_user)
        await redis_server.invalidate_token(token_jti, remaining_time)
        logger.info(f"Password changed for user: {db_user.id}")
        return True

    
    
    async def logout(self, access_token: str, refresh_token: str) -> bool:
        
        access_payload = security.decode_token(access_token)
        access_jti = access_payload.get("jti")
        if await redis_server.is_token_blacklisted(access_jti):
            raise exceptions.BadRequestError("Token revoked")
        
        refresh_payload = security.decode_token(refresh_token)
        if not refresh_payload or refresh_payload.get("type") != "refresh":
            raise exceptions.BadRequestError("Invalid token type")
        
        refresh_exp = max(refresh_payload.get("exp") - int(time.time()), 1)
        # compute the remaining time in the token so it deletes in redis the same time it TTL expires
        refresh_jti = refresh_payload.get("jti")
        await redis_server.invalidate_token(refresh_jti, refresh_exp)
        
        access_exp = max(access_payload.get("exp") - int(time.time()), 1)
        
        await redis_server.invalidate_token(access_jti, access_exp)
        
        user_id = access_payload.get("sub")
        refresh_key = self._get_refresh_key(user_id)
        await redis_server.delete_cache(refresh_key)

        logger.info(f"Successful logout for user: {user_id} on current device session.")
            
        return True






