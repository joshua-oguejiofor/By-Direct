from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, Payment, Product, Profile, User
from app.shared.utility import date_bucket_expr


class AnalyticsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    
    
    async def customer_analytics(self, start: datetime, end: datetime, condition: str) -> tuple:
        
        window = and_(Order.created_at >= start, Order.created_at < end, Order.status.in_(condition))
        
        total_customers = (
            await self.db.execute(
            select(func.count(User.id)))
            ).scalar_one()
        
        new_customers = (
            await self.db.execute(
                select(func.count(User.id))
                .where(
                    User.created_at >= start, 
                    User.created_at < end
                )
            )
        ).scalar_one()

        # A "customer" here = a user with >=1 paid order in the window (for
        # returning) or ever (for spending averages).
        order_counts_subquery = (
            select(Order.user_id, func.count(Order.id).label("order_count"))
            .where(window)
            .group_by(Order.user_id)
            .subquery()
        )

        returning_customers = (
            await self.db.execute(
                select(func.count())
                .select_from(order_counts_subquery)
                .where(
                    order_counts_subquery.c.order_count > 1
                )
            )
        ).scalar_one()

        customers_with_purchase = (
            await self.db.execute(
                select(func.count())
                .select_from(order_counts_subquery))
        ).scalar_one()

        customers_without_purchase = int(total_customers) - int(customers_with_purchase)

        avg_spend = (
            await self.db.execute(
                select(func.coalesce(func.avg(Order.total_amount), 0))
                .where(window)
            )
        ).scalar_one()
        
        return (total_customers, new_customers, returning_customers, customers_with_purchase, customers_without_purchase, avg_spend)
    
    
    async def top_customers(self, start: datetime, end: datetime, limit: int, order_by: str, condition: str) -> list:
        
        """order_by: 'spending' or 'orders'"""
        spend = func.coalesce(func.sum(Order.total_amount), 0).label("total_spent")
        order_count = func.count(Order.id).label("order_count")
        last_order = func.max(Order.created_at).label("last_order_date")

        rows = (await self.db.execute(
            select(
                User.id, User.email, 
                Profile.first_name, 
                Profile.last_name, 
                order_count, spend, 
                last_order
                )
            .join(Profile, Profile.user_id == User.id)
            .join(Order, Order.user_id == User.id)
            .where(
                Order.created_at >= start, 
                Order.created_at < end, 
                Order.status.in_(condition)
                )
            .group_by(User.id, User.email, Profile.last_name)
            .order_by((spend if order_by == "spending" else order_count).desc())
            .limit(limit)
        ))
        return rows.all()
    
    #  No async need as O/I wasn't performed
    def _selling_product(self, start: datetime, end: datetime, condition: set) -> tuple:
        
        # """sort_by: 'quantity' | 'revenue'"""
                
        qty = func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity_sold")
        rev = func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0).label("revenue")
        order_count = func.count(func.distinct(OrderItem.order_id)).label("order_count")
        
        query = (
        select(Product.id, Product.name, qty, rev, order_count)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.created_at >= start, 
            Order.created_at < end, 
            Order.status.in_(condition)
            )
        .group_by(Product.id, Product.name))
        
        return (query, rev, qty)
    
    
    async def top_selling_or_revenue_product(self, limit: int, sort_by: str, start: datetime, end: datetime, condition: set) -> list:
        
        """sort_by: 'quantity' | 'revenue'"""
        query, rev, qty = self._selling_product(start, end, condition)
        rows = query.order_by(
            (rev if sort_by == "revenue" else qty).desc()).limit(limit)
        
        return (await self.db.execute(rows)).all()
    
    
    
    async def low_inventory_stocks(self, offset: int, limit: int, quantity: int) -> tuple[list, int]:
        result = (await self.db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(Product.stock_quantity <= quantity)
            .offset(offset)
            .limit(limit)
            .order_by(Product.stock_quantity.asc())
        )).scalars().all()
        
        count = (await self.db.execute(
            select(func.count(Product.id))
            .where(Product.stock_quantity <= quantity)
            )).scalar_one()
        
        return result, count
    
    async def low_selling_product(self, limit: int, start: datetime, end: datetime, condition: set) -> list:
        
        query, _ , qty = self._selling_product(start, end, condition)  
        rows = (
            query.having(qty > 0)
            .order_by(
            (qty).asc())
            .limit(limit)
            )
        
        return (await self.db.execute(rows)).all()
        
    async def zero_sales_product(self, start: datetime, end: datetime, condition: set) -> list:
        
        sub_query = (
        select(OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.product_id == Product.id,
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.in_(condition)        
            )
        )
        rows = await self.db.execute(
            select(Product.id, Product.name, Product.created_at)
            .where(
                Product.is_active.is_(True), 
                ~sub_query.exists() # ~ is a not operator, so this condition checks where the product don't have sales
                )
            .order_by(Product.created_at.desc())
        )
        return rows.all()


    async def overview(
        self, 
        condition: str, 
        pending: str,
        cancelled: str,
        start: datetime, 
        end: datetime,
        ) -> tuple:
        
        window = and_(Order.created_at >= start, Order.created_at < end)
        
        revenue_row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(Order.total_amount), 0).label("total_revenue"),
                    func.count(Order.id).label("total_orders"),
                    func.coalesce(func.avg(Order.total_amount), 0).label("avg_order_value"),
                ).where(window, Order.status.in_(condition))
            )
        ).one()

        items_sold = (
            await self.db.execute(
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .join(Order, Order.id == OrderItem.order_id)
                .where(window, Order.status.in_(condition))
            )
        ).scalar_one()

        status_counts_row = (
            await self.db.execute(
                select(
                    func.coalesce(
                        func.sum(case((Order.status == pending, 1), else_=0)), 0
                    ).label("pending"),
                    func.coalesce(
                        func.sum(case((Order.status == "delivered", 1), else_=0)), 0
                    ).label("delivered"),
                    func.coalesce(
                        func.sum(case((Order.status == cancelled, 1), else_=0)), 0
                    ).label("cancelled"),
                ).where(window)
            )
        ).one()
        
        total_users = (await self.db.execute(
            select(func.count(func.distinct(User.id)))
            .where(User.created_at < end)
        )).scalar_one()
        
        total_product = (await self.db.execute(
            select(func.count(Product.id))
            .where(Product.is_active.is_(True))
        )).scalar_one()

        
        return (revenue_row, items_sold, status_counts_row, total_users, total_product)
    
    async def order_revenue_series(
        self, 
        grouping: str, 
        start: datetime,
        end: datetime,
        condition: str,     
    ) -> list:
        
        bucket = date_bucket_expr(Order.created_at, grouping).label("bucket_date")
        result = await self.db.execute(
            select(bucket, func.coalesce(func.sum(Order.total_amount), 0).label("revenue"))
            .where(
                Order.created_at >= start, 
                Order.created_at < end, 
                Order.status.in_(condition)
                )
            .group_by(bucket)
            .order_by(bucket)
        )
        return result.all()
    
    async def period_revenue(self, start: datetime, end: datetime, condition: str) -> int:
        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Order.total_amount), 0))
            .where(
                Order.created_at >= start, 
                Order.created_at < end, 
                Order.status.in_(condition))
            )
        return result.scalar_one()
    
    async def order_analysis(self, start: datetime, end: datetime, grouping: str) -> tuple:
            window = and_(Order.created_at >= start, Order.created_at < end)
            bucket = date_bucket_expr(Order.created_at, grouping).label("bucket_date")
            
            total = (await self.db.execute(
                select(func.count(Order.id))
                .where(window))).scalar_one()
    
            status_rows = (await self.db.execute(
                select(Order.status, func.count(Order.id))
                .where(window)
                .group_by(Order.status))
                ).all()
            
            series_rows = (await self.db.execute(
                select(bucket, func.count(Order.id).label("order_count"))
                    .where(window)
                    .group_by(bucket)
                    .order_by(bucket)
                )).all()
            return (total, status_rows, series_rows)
        
    async def payment_analysis(self, start: datetime, end: datetime) -> tuple:
        counts_row = await self.db.execute(
            select(
                func.coalesce(func.sum(case((Payment.status == "completed", 1), else_=0)), 0),
                func.coalesce(func.sum(case((Payment.status == "failed", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Payment.status == "pending", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Payment.status == "cancelled", 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((Payment.status == "completed", Payment.amount), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Payment.status == "refunded", Payment.amount), else_=0)), 0
            ),
            func.count(Payment.id),
        )
        .where(
            Payment.created_at >= start, 
            Payment.created_at < end)
        )
        return counts_row.one()
        
        
        
    async def period_comparison(self, start: datetime, end: datetime, condition: str) -> tuple:
        
        row = await self.db.execute(
            select(
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(Order.id),
                func.coalesce(func.avg(Order.total_amount), 0),
                func.count(func.distinct(Order.user_id)),
            ).where(
                Order.created_at >= start, 
                Order.created_at < end, Order.status.in_(condition)
                ))
        
        return row.one()

