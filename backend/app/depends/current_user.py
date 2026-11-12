import logging
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import exceptions
from app.core.database import get_db
from app.core.redis_server import is_token_blacklisted
from app.core.security import decode_token
from app.domains.auth.auth_repository import AuthRepository
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]

async def get_current_user(db: DBSessionDep, token: str = Depends(oauth2_scheme)) -> User:
    
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_token(token)

    except (exceptions.BadRequestError, exceptions.UnauthorizedError):
        raise credentials_exception

    if not payload or payload.get("type") != "access":
        raise credentials_exception
    
    if await is_token_blacklisted(payload.get("jti")):
            raise credentials_exception
    

    user_id = payload.get("sub")
    repo = AuthRepository(db)
    user = await repo.get_by_id(user_id)
    if not user or not user.is_active or user.is_deleted == True:
        raise credentials_exception
    return user


current_user_ = Annotated[User, Depends(get_current_user)]


async def get_admins(current_user: current_user_) -> User:
    
    if current_user.role != UserRole.ADMIN and current_user.role != UserRole.SUPERADMIN:
        raise exceptions.ForbiddenError("Admin access required")
    return current_user


async def get_superadmin(superuser: current_user_) -> User:
    
    if superuser.role != UserRole.SUPERADMIN:
        raise exceptions.ForbiddenError("Unauthorised access")
    return superuser
 