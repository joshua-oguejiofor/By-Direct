import logging
from datetime import UTC, datetime
from math import ceil

from app.core import exceptions
from app.core.config import settings
from app.core.enums import UserRole
from app.models import Profile, User

from .user_repository import UserRepository
from .user_schema import UpdateProfile, UserProfile

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
      
      
    async def create_profile(self, current_user: User, data: UserProfile)-> bool:
        if await self.user_repo.check_user(current_user.id):
            raise exceptions.ConflictingError("Profile already exist.")
        
        profile = Profile(
            user_id=current_user.id,
            first_name=data.first_name,
            last_name=data.last_name,
            phone_number=data.phone_number,
            address=data.address,
            country=data.country,
            city=data.city
        )
        
        await self.user_repo.save_user(profile)
        return True
        
    # Uer viewing his/her profile or an admin
    async def user_profile(self, current_user: User, user_id: int) -> Profile:
        
        # Authorization check: Non-admins can only view their own profile
        if user_id != current_user.id and current_user.role not in settings.ADMINS:
            raise exceptions.ForbiddenError("Not authorized to view this profile")
        
        db_user = await self.user_repo.get_current_user(user_id)
        if not db_user:
            raise exceptions.NotFoundError("Profile not found")
                
        return db_user
    
    
    
    async def update_my_profile(self, data: UpdateProfile, current_user: User) -> bool:
        
        db_profile = await self.user_repo.get_user(current_user.id)
        if not db_profile:
            raise exceptions.NotFoundError("Profile not found.")
        
        for field, value in data.model_dump(exclude_unset=True).items():
                setattr(db_profile, field, value)
        
        await self.user_repo.update_user(current_user)
        return True
        
        
    async def all_users(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        
        users, count = await self.user_repo.get_all_users(offset=offset, limit=page_size)
        
        total_pages = ceil(count / page_size) if count > 0 else 1
                
        return {
            "users": users,
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
        
    
    async def deactivate_user_account(self, current_user: User, user_id: int | None = None) -> dict:
                
        # Authorization check: Non-admins can only view their own profile
        if user_id != current_user.id and current_user.role not in settings.ADMINS:
            raise exceptions.ForbiddenError("Not authorized for deactivation.")
                
        # get both user and profile using the relationship
        db_user = await self.user_repo.get_current_user(user_id)
        if not db_user:
            raise exceptions.NotFoundError("Profile not found.")
        
        if db_user.user.role == UserRole.SUPERADMIN:
            raise exceptions.ForbiddenError("Deactivation for super-admin not allowed")
        
        msg = "deactivated"
    
        if db_user.user.is_active == False and current_user.role in settings.ADMINS:
            
            # --- ACTIVATION LOGIC ---
            db_user.user.is_active = True
            db_user.user.is_deleted = False
            db_user.user.deleted_at = None
            msg = "activated" # override the default message for admin activating a user
        else:
            # --- DEACTIVATION LOGIC ---
            db_user.user.is_active = False
            db_user.user.is_deleted = True
            db_user.user.deleted_at = datetime.now(UTC)
        await self.user_repo.update_user(db_user)
        logger.info(f"Account for: {db_user.id} {msg} by user: {user_id}")
        return {"msg": f"Account {msg}"}

    
    async def search_users(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> dict:
        
        offset = (page - 1) * page_size
        users, count = await self.user_repo.search_users(
            search=search,
            role=role,
            is_active=is_active,
            offset=offset,
            limit=page_size
        )
        
        # Constructed pagination metadata response
        total_pages = ceil(count / page_size) if count > 0 else 1
        
        return {
            "users": users,
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }