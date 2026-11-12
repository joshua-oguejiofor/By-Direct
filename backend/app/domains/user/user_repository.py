from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Profile, User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def check_user(self, user_id: int) -> bool:
        return bool((await self.db.execute(
            select(exists().where(Profile.user_id == user_id)))).scalar()
                    )
       
    async def get_current_user(self, user_id: int) -> Profile | None:
        result =  await self.db.execute(
            select(Profile)
            .options(selectinload(Profile.user))
            .where(Profile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user(self, user_id: int) -> Profile | None:
        result = await self.db.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all_users(self, offset: int, limit: int) -> tuple[list[Profile], int]:
        users = (await self.db.execute(
            select(Profile)
            .options(selectinload(Profile.user))
            .offset(offset)
            .limit(limit)
            .order_by(Profile.id)
        )).scalars().all()
        
        total_count = (await self.db.execute(
            select(func.count(Profile.id)))).scalar_one()
        
        return users, total_count
    
            
    async def search_users(
        self,
        offset: int,
        limit: int,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        
        # Base query starting from User and joining Profile
        query = (select(User)
                 .options(selectinload(User.profile))
                 .join(User.profile)
                 )
        
        # Dynamic filters
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    User.email.ilike(search_term),
                    Profile.first_name.ilike(search_term),
                    Profile.last_name.ilike(search_term)
                )
            )
        if role is not None:
            query = query.where(User.role == role)
            
        if is_active is not None:
            query = query.where(User.is_active == is_active)
            
        # 3. Calculate total matching records using the subquery count pattern
        count = (await self.db.execute(
            select(func.count())
            .select_from(query.subquery())
        )).scalar_one()
                
        users = (await self.db.execute(
            query.offset(offset)
            .limit(limit)
            .order_by(Profile.id)
            )
                 ).scalars().all()
                
        return users, count
    
    async def save_user(self, obj: Profile) -> Profile:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
        
    async def update_user(self, obj: Profile) -> Profile:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj


