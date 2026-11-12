import logging
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core import exceptions
from app.core.config import settings

logger = logging.getLogger(__name__)

password_handler = PasswordHasher()


def hash_user_password(password: str) -> str:
    """Hashes a plain text password using Argon2id."""
    return password_handler.hash(password)


def verify_user_password(plain_password: str, hashed_password: str ) -> bool:
    """Verifies a plain text password against an Argon2 hash."""
    try:
        return password_handler.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False


def generate_otp()-> str:
    return secrets.token_hex(32)



def create_access_token(data: dict) -> str:
    user_data = data.copy()
    
    exp = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_data.update({"exp": exp, "type": "access"})
    return jwt.encode(
        user_data, key=settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM)
    
    
def create_refresh_token(data: dict) -> str:
    user_data = data.copy()
        
    exp = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    user_data.update({"exp":exp, "type": "refresh"})    
    return jwt.encode(
        user_data, key=settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM)
    

def password_reset_token(data: dict) -> str:
    user_data = data.copy()
        
    exp = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    user_data.update({"exp":exp, "type": "password_reset"})    
    return jwt.encode(
        user_data, key=settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM)
    
    
def create_email_verification_token(data: dict) -> str:
    user_data = data.copy()
    exp = datetime.now(UTC) + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
    
    user_data.update({"exp":exp, "type":"verify_email"})
    return jwt.encode(
        user_data, 
        key=settings.SECRET_KEY.get_secret_value(), 
        algorithm=settings.ALGORITHM
        )
    
    
def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM]
        )
    except jwt.ExpiredSignatureError as e:
        logger.warning(f"Expired token: {e}")
        raise exceptions.BadRequestError("Session has expired")

    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise exceptions.UnauthorizedError("Invalid token")

    return payload


