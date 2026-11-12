
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review


class ReviewRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def get_user_review(self, user_id: int, product_id: int) -> bool:
        result = await self.db.execute(
            select(exists().where(
                Review.user_id == user_id, 
                Review.product_id == product_id)
            
            ))
        return bool(result.scalar())
    
    async def get_review(self, review_id: int) -> Review | None:
        result = await self.db.execute(
            select(Review)
            .where(Review.id == review_id)
        )
        return result.scalar_one_or_none()
    
    async def get_produce_review_rating(self, product_id: int) -> tuple[int, int]:
        avg_result = await self.db.execute(
            select(
                func.avg(Review.rating), 
                func.count(Review.id)
                )
            .where(Review.product_id == product_id, Review.is_approved.is_(True))
        )
        avg_rating, count = avg_result.one()
        
        return avg_rating, count


    async def all_product_reviews(
        self, 
        product_id: int, 
        skip: int, 
        page_size: int,
        is_admin: bool = False,
        ) -> tuple[list[Review], int]:
        
        query = select(Review).where(Review.product_id == product_id)
        
        if not is_admin: 
            query = query.where(Review.is_approved.is_(True))
        
        count = (await self.db.execute(
            select(func.count(Review.id))
            .select_from(query.subquery())
            )).scalar_one()
        
        # Get the paginated reviews
        reviews = (await self.db.execute(
            query.order_by(Review.created_at)
            .offset(skip)
            .limit(page_size)
        )).scalars().all()
        
        return reviews, count



    async def save_review(self, obj: Review) -> Review:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    async def update_review(self, obj: Review) -> Review:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    async def delete_review(self, obj: Review) -> None:
        await self.db.delete(obj)
        await self.db.flush()






