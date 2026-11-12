from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import EmailStr

from app.depends import current_user, di_injection
from app.middleware.rate_limit import limiter
from app.models.user import User

from . import auth_schema
from .auth_service import AuthService

current_user_ = Annotated[User, Depends(current_user.get_current_user)]
auth_service_ = Annotated[AuthService, Depends(di_injection.get_auth_service)]

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

"""Register new user account."""
@router.post("/register", status_code=201)
async def register(
        data: auth_schema.CreateUser,
        service: auth_service_,
        background_tasks: BackgroundTasks,
) -> dict[str, str]:
    await service.register(data=data, background_tasks=background_tasks)
    return {"msg": "Check your email to continue verification process."}


@router.post('/register/resend-email', status_code=200)
@limiter.limit("5/minute")
async def resend_email(
        request: Request,
        data: auth_schema.EmailVerification,
        service: auth_service_,
        background_tasks: BackgroundTasks
) -> dict[str, str]:
    
    await service.resend_email(email=data.email, background_tasks=background_tasks)
    return {"msg": "Check your email to continue verification process."}


@router.get('/verify-email', status_code=302, response_class=RedirectResponse) # this redirect the user to the login page
@limiter.limit("5/minute")
async def verify_token(
        request: Request,
        token: str,
        service: auth_service_
):
    return await service.email_verify_token(token)


@router.post("/login", response_model=auth_schema.TokenResponse, status_code=200)
@limiter.limit("5/minute")
async def login(
        request: Request,
        service: auth_service_,
        background_tasks: BackgroundTasks,
        username: EmailStr = Form(...),  # noqa: B008
        password: str = Form(..., min_length=8),
        
):
    return await service.login(email=username, password=password, background_tasks=background_tasks, request=request)


"""Rotate refresh token and get a new access token."""
@router.post("/refresh", response_model=auth_schema.TokenResponse, status_code=200)
async def refresh(
        data: auth_schema.RefreshTokenRequest,
        service: auth_service_
):
    return await service.refresh_token(data.refresh_token)


@router.patch('/password', status_code=200)
@limiter.limit("5/minute")
async def change_password(
        request: Request,
        data: auth_schema.ChangePassword,
        current_user: current_user_,
        service: auth_service_
) -> dict[str, str]:
    
    await service.change_password(data.old_password, data.new_password, user=current_user)
    return {"msg": "Password update successful"}


@router.post('/forget-password', status_code=200)
@limiter.limit("5/minute")
async def forget_password(
        request: Request,
        data: auth_schema.EmailVerification,
        service: auth_service_,
        background_tasks: BackgroundTasks
) -> dict[str, str]:
    
    await service.forget_password(email=data.email, background_task=background_tasks)
    return {"msg": "If the account exists, an OTP has been sent"}


@router.post('/verify-otp', status_code=200)
@limiter.limit("5/minute")
async def verify_otp(
        request: Request,
        data: auth_schema.OTPVerify,
        service: auth_service_
) -> dict[str, str]:
    
    return await service.verify_otp(email=data.email, otp=data.otp)


@router.post("/reset-password", status_code=200)
@limiter.limit("5/minute")
async def reset_password(
        request: Request,
        data: auth_schema.PasswordReset,
        service: auth_service_
) -> dict[str, str]:
    
    await service.reset_password(reset_token=data.reset_token, new_password=data.new_password)

    return {"msg": "Password reset successfully"}


"""Logout and invalidate both access and refresh tokens."""
@router.post("/logout", status_code=200)
@limiter.limit("5/minute")
async def logout(
    request: Request,
    refresh_data: auth_schema.RefreshTokenRequest,
    service: auth_service_,
    access_token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    
    await service.logout(access_token=access_token, refresh_token=refresh_data.refresh_token)
    return {"msg": "Logged out successfully"}

