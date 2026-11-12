import logging

from slugify import slugify

from app.core import exceptions, redis_server
from app.core.config import settings
from app.models import Category, User

from .category_repository import CategoryRepository
from .category_schema import AddCategory

logger = logging.getLogger(__name__)

class CategoryService:
    def __init__(self, category_repo: CategoryRepository):
        self.category_repo = category_repo


    async def create_category(self, data: AddCategory, admin_user: User) -> bool:
        
        if await self.category_repo.check_category(data.name):
            raise exceptions.ConflictingError("Category name already exist.")
        
        category = Category(
            name=data.name,
            slug=slugify(data.name),
            description=data.description,
            parent_id=data.parent_id,
        )
        await redis_server.delete_cache(settings.CATEGORY_CACHE_PRIFIX)
        await self.category_repo.add_category(category)
        logger.info(f"Category with id: {category.id} created by admin {admin_user.id}")
        return True

    async def get_all_categories(self) -> Category | dict:
        
        cached = await redis_server.get_analysis_cache(settings.CATEGORY_CACHE_PRIFIX)
        if cached:
            return cached
        
        categories = await self.category_repo.get_all()
        await redis_server.set_cache(key=settings.CATEGORY_CACHE_PRIFIX, value=categories)
        
        return  categories

    async def get_category_by_id(self, category_id: int) -> Category:
                
        db_category = await self.category_repo.category_by_id(category_id)
        
        if not db_category:
            raise exceptions.NotFoundError("Category not found.")
        
        return db_category

    
    async def update_category(self, category_id: int, data: AddCategory, admin_user: User) -> bool:
                
        db_category = await self.get_category_by_id(category_id)
        
        # Get only fields actually provided and convert to dictonary
        save_data = data.model_dump(exclude_unset=True)

        if data.name and await self.category_repo.check_category(data.name, category_id=category_id):
            raise exceptions.ConflictingError(f"Category {db_category.name} already exist.")

        # Update the fields
        for field, value in save_data.items():
            setattr(db_category, field, value)

        db_category.slug = slugify(data.name) 
        await self.category_repo.update_category(db_category)
        await redis_server.delete_cache(settings.CATEGORY_CACHE_PRIFIX)
        logger.info(f"Category with id: {db_category.id} updated by admin {admin_user.id}")
        return True

    async def remove_category(self, category_id: int, superadmin_user: User) -> bool:
                        
        if await self.category_repo.category_has_products(category_id):
            raise exceptions.BadRequestError("Category still has valid products.")
                
        if not await self.category_repo.delete_category(category_id):
            raise exceptions.NotFoundError(f"Category for {category_id} not found")
        
        await redis_server.delete_cache(settings.CATEGORY_CACHE_PRIFIX)
        logger.info(f"Category with id: {category_id} deleted by admin {superadmin_user.id}")
        return True