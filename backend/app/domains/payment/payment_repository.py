
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment


class PaymentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def get_payment_by_order_id(self, order_id: int) -> Payment | None:
        result = await self.db.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
        )
        
        return result.scalar_one_or_none()
    
    
    async def get_by_id_or_refrence(
        self, 
        payment_id: int| None = None, 
        provider_reference: str | None = None,
        order_id : int | None = None
        ) -> Payment | None:
        
        query = select(Payment)
        
        print("pay", payment_id, "refernce:", provider_reference, "order id", order_id)
        if payment_id is not None:
            query = query.where(Payment.id == payment_id)

        if provider_reference is not None:
            query = query.where(Payment.provider_reference.ilike(f"%{provider_reference}%"))
        
        if order_id is not None:
            query = query.where(Payment.order_id == order_id)
        
        print("Query:", query)             
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    async def get_all_payment(self, skip: int, limit: int, provider: str | None = None) -> tuple[list[Payment], int]:
        
        query = select(Payment)

        if provider:
            query = query.where(Payment.provider == provider)
            
        count = (await self.db.execute(
            select(func.count()).select_from(query.subquery())
            )).scalar_one()
                    
        result = (await self.db.execute(
            query
            .offset(skip)
            .limit(limit)
            .order_by(Payment.id)
        )).scalars().all()
        
        return result, count
    

    async def delete_payment(self, payment_id: int) -> bool:
        result = await self.db.execute(
            delete(Payment)
            .where(Payment.id == payment_id)
        )
        return result.rowcount > 0
        
        
        
    async def add_payment(self, obj: Payment) -> Payment:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    async def update_payment(self, obj: Payment) -> Payment:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    