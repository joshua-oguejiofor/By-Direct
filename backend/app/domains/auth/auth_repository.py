from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def validate_user_refr_token(self, user_id: int) -> bool:
        result = await self.db.execute(
            select(
                exists().
                where(
                    User.id == user_id,
                    User.is_active == True,
                    User.is_deleted == False
                    )
                )
            )
        return bool(result.scalar())

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.scalar(
            select(User)
            .where(User.id == user_id)
        )

    async def get_email(self, email: str) -> User | None:
        return await self.db.scalar(
            select(User)
            .where(User.email == email)
        )
    
    async def check_email_exist(self, email: str) -> bool:
        result = await self.db.execute(
            select(exists().where(User.email == email)
                   ))
        return bool(result.scalar())
        
        
    async def login_user(self, email: str) -> User | None:
        user = await self.db.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.email == email, User.is_deleted == False)    
        )
        return user.scalar_one_or_none()
        

    async def save_user(self, obj: User) -> User:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
        
    async def update_user(self, obj: User) -> User:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj