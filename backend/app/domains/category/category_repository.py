from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category


class CategoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def check_category(self, category_name: str, category_id: int | None = None) -> bool:
        query = select(Category).where(Category.name == category_name)
        
        if category_id is not None:
            query = query.where(Category.id != category_id)
            
        result = await self.db.execute(select(query.exists()))
        return bool(result.scalar())  # Returns 1/0 directly from the database then converted to bool value
       
        
    async def get_all(self) -> list[Category]:
        # 1. Fetch the paginated slice of categories
        return  (
            await self.db.execute(
            select(Category)
            .order_by(Category.name)           
        )).scalars().all()

    
    async def category_by_id(self, category_id: int) -> Category | None:
            result = await self.db.execute(
                select(Category)
                .where(Category.id == category_id)
            )
            return result.scalar_one_or_none()
        
    async def category_has_products(self, category_id: int) -> bool:
        """
        Checks if a category has any related products using the relationship 
        without.
        """
        result = await self.db.execute(
            select(exists()
            .where(
                Category.id == category_id, 
                Category.products.any()
                   ) # Evaluates the relationship existence
            ))
        return bool(result.scalar())
        
    async def add_category(self, obj: Category) -> Category:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
        
    async def update_category(self, obj: Category) -> Category:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj


    async def delete_category(self, category_id: int) -> bool:
        result = await self.db.execute(
            delete(Category)
            .where(Category.id == category_id)
        )
        await self.db.flush()
        return result.rowcount > 0 # returns True/False
        
        
    
