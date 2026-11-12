import logging
from math import ceil

from app.core import exceptions
from app.domains.order.order_service import OrderService
from app.domains.product.product_service import ProductService
from app.models import User
from app.models.review import Review
from app.shared.utility import admin_check, sanitize_input

from .review_repository import ReviewRepository
from .review_schema import ReviewCreate

logger = logging.getLogger(__name__)

class ReviewService:
    def __init__(
        self, 
        review_repo: ReviewRepository, 
        order_service: OrderService = None, 
        product_service: ProductService = None
    ):
        self.review_repo = review_repo
        self.order_service = order_service
        self.product_service = product_service

    async def create_review(self, current_user: User, data: ReviewCreate) -> Review:
        
        if await self.review_repo.get_user_review(user_id=current_user.id, product_id=data.product_id):
            raise exceptions.BadRequestError("You have already reviewed this product")

        # Check purchase status using OrderService
        if not await self.order_service.has_user_purchased_product(
            current_user=current_user, product_id=data.product_id
            ):
            raise exceptions.ForbiddenError("No record of purchase for this product found, review not allowed.")
        
        review = Review(
            user_id=current_user.id,
            product_id=data.product_id,
            rating=data.rating,
            comment=sanitize_input(data.comment), # this avouds malware placed in the input
            is_verified_purchase=True
        )
        await self.review_repo.save_review(review)

        # Update product rating
        avg_rating, count = await self.review_repo.get_produce_review_rating(data.product_id)
        await self.product_service._update_product_rating_reviews(
            current_user=current_user,
            product_id=data.product_id, 
            avg_rating=avg_rating, 
            total_reviews=count
            )
        logger.info(f"Review {review.id} added by user: {current_user.id} on product {data.product_id}")
        return review

    async def get_product_reviews(self, product_id: int, page: int, page_size: int, current_user: User):
        skip = (page - 1) * page_size
        
        is_admin = admin_check(current_user)
        reviews, count = await self.review_repo.all_product_reviews(
            product_id=product_id, skip=skip, page_size=page_size, is_admin=is_admin
            )
        # Constructed pagination metadata response
        total_pages = ceil(count / page_size) if count > 0 else 1
        
        return {
            "reviews": reviews,
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
        
        
    async def approve_review(self, review_id: int, admin_user: User) -> dict:
        
        db_review = await self.review_repo.get_review(review_id)
        if not db_review:
            raise exceptions.NotFoundError("Review not found.")
        
        if db_review.is_verified_purchase == False:
            raise exceptions.ForbiddenError("Purchase for this product has not been verified.")
        
        msg = "Approved"
        
        if db_review.is_approved == True:
            db_review.is_approved = False
            msg = "Rejected"
        else:
            db_review.is_approved = True
            
        await self.review_repo.update_review(db_review)
        
        # Update product rating
        avg_rating, count = await self.review_repo.get_produce_review_rating(db_review.product_id)
        await self.product_service._update_product_rating_reviews(
            current_user=admin_user,
            product_id=db_review.product_id, 
            avg_rating=avg_rating, 
            total_reviews=count
            )
        logger.info(f"Review {db_review.id} {msg} by admin: {admin_user.id}")
        return {"msg": f"review {msg} successfully"}
    
    
    
    async def delete_review(self, review_id: int, admin_user: User) -> bool:
        
        db_review = await self.review_repo.get_review(review_id)
        
        if not db_review:
            raise exceptions.NotFoundError("Review not found")
        
        await self.review_repo.delete_review(db_review)
        
        # Update product rating
        avg_rating, count = await self.review_repo.get_produce_review_rating(db_review.product_id)
        await self.product_service._update_product_rating_reviews(
            current_user=admin_user,
            product_id=db_review.product_id, 
            avg_rating=avg_rating, 
            total_reviews=count
            )
        logger.info(f"Review {db_review.id} deleted by user: {admin_user.id}")
        return True
        
        
    
        
        
