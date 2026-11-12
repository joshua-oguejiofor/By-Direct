"""
This modeule is responsible for registering an admin user in the database if it does not already exist. 
It checks for the existence of a user with the email specified in the settings
Creates one with the provided password and role if not found.
"""


from sqlalchemy import exists, select

from app.core import config, database, enums, security
from app.models.user import Profile, User

settings = config.settings
async_session = database
hash_pswd = security

async def register_superadmin_user():
    async with async_session.AsyncSessionLocal() as db:
        existing_user= await db.scalar(
            select(exists())
            .where(User.email == settings.SUPERADMIN_EMAIL)
            )
        
        if existing_user:
            return True
        
        admin_profile = Profile(
            first_name= settings.SUPERADMIN_FIRST_NAME,
            last_name= settings.SUPERADMIN_LAST_NAME,
            phone_number=settings.SUPERADMIN_PHONE
        )
         
        admin_user= User(
            email= settings.SUPERADMIN_EMAIL, 
            hashed_password= hash_pswd.hash_user_password(settings.SUPERADMIN_PASSWORD.get_secret_value()),
            is_active= True, 
            is_verified= True, 
            role= enums.UserRole.SUPERADMIN,
            profile=admin_profile
            )
        db.add(admin_user) 
        await db.commit()
        await db.refresh(admin_user)
        return True
    
        
    