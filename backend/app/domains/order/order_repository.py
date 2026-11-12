from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderItem


class OrderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def my_orders(self, user_id, skip: int, limit: int) -> list[Order]:
        orders = (await self.db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .offset(skip).limit(limit)
        )).scalars().all()
        
        total_count = (await self.db.execute(
            select(func.count(Order.id))
            .where(Order.user_id == user_id)
            )).scalar_one()
        
        return orders, total_count
    
    
    async def all_orders(self, skip: int, limit: int) -> list[Order]:
        orders = (await self.db.execute(
            select(Order)
            .order_by(Order.created_at.desc())
            .offset(skip).limit(limit)
        )).scalars().all()
        
        total_count = (await self.db.execute(
            select(func.count(Order.id))
            )).scalar_one()
        
        return orders, total_count


    async def get_with_items(self, order_id) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .options(
                selectinload(Order.items), 
                selectinload(Order.payment)
                )
            
            .where(Order.id == order_id)
        )
        return result.scalar_one_or_none()


    async def get_by_order_id(self, order_id: int) -> Order | None:
        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id).with_for_update()
        )
        return result.scalar_one_or_none()


    async def check_expired_order(self, order_status: str, expire: datetime):
        result = await self.db.execute(
            select(Order)
            .options(selectinload(Order.payment))
            .options(selectinload(Order.items))
            .where(
                Order.status == order_status,
                Order.expiration_cutoff <= expire
            ).with_for_update(skip_locked=True) # skipp a row that is locked to avoid modification
        )
                
        return result.scalars().all()    
    
    
    async def exists_completed_order_for_product(self, user_id: int, product_id: int, status: list) -> bool:
        
        """
        Check if a user has a paid/completed order for a specific product.
        Used during review creation to set `is_verified_purchase = True`.

        Queries using an optimized nested `EXISTS` subquery to short-circuit 
        immediately on the first matching record.
        """ 
        result = await self.db.execute(
            select(
                exists()
                .where(
                Order.user_id == user_id,
                Order.status.in_(status),
                OrderItem.order_id == Order.id,
                OrderItem.product_id == product_id,
            ))
        )
        return bool(result.scalar())
   
    async def save_order(self, obj: Order):
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    
    async def update_order(self, obj: Order):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj


    # async def delete(self, obj: Order) -> None:
    #     await self.db.delete(obj)
    #     await self.db.flush()
    
