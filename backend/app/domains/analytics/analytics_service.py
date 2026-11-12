from datetime import datetime
from decimal import Decimal
from math import ceil

from app.core.config import settings
from app.core.enums import Grouping, OrderStatus
from app.core.redis_server import get_analysis_cache, set_analysis_cache
from app.depends.analitics_depends import ResolvedRange
from app.shared.utility import (
    build_cache_key,
    grouping_for,
    safe_growth_pct,
)

from .analitics_repository import AnalyticsRepository

PAID_ORDER_STATUSES = settings.ANALYTICS_ORDER_STATUSES

class AnaliticsService:
    def __init__(self, analytics_repo: AnalyticsRepository):
        self.analytics_repo = analytics_repo
        

# =============================================================================
# 1. Overview
# =============================================================================

    async def get_overview(self, rng: ResolvedRange) -> dict:
        
        key = build_cache_key("overview", rng.label)
        
        overview = await get_analysis_cache(key)
        if overview:
            return overview
        
        (revenue_row, items_sold, status_counts_row, 
         total_customers, total_products) = await self.analytics_repo.overview(
            condition=PAID_ORDER_STATUSES, pending=OrderStatus.PENDING, 
            cancelled=OrderStatus.CANCELLED, start=rng.start, end=rng.end
            )
        
        response = {
            "total_revenue": Decimal(revenue_row.total_revenue),
            "total_orders": int(revenue_row.total_orders),
            "total_customers": int(total_customers),
            "total_products": int(total_products),
            "average_order_value": Decimal(revenue_row.avg_order_value).quantize(Decimal("0.01")),
            "total_items_sold": int(items_sold),
            "pending_orders": int(status_counts_row.pending),
            "delivered_orders": int(status_counts_row.delivered),
            "cancelled_orders": int(status_counts_row.cancelled),
            "period_start": rng.start,
            "period_end": rng.end,
        }
        
        await set_analysis_cache(key, expire=settings.CACHE_TTL_OVERVIEW, value=response)
        
        return response

    # 2. Revenue analytics
    async def get_revenue_analytics(self, rng: ResolvedRange, grouped_data: Grouping) -> dict:
        
        grouped_data = grouping_for(rng, grouped_data)
        key = build_cache_key("revenue", rng.label, grouped_data.value)
        
        revenue = await get_analysis_cache(key)
        if revenue is not None:
            return revenue
        
        
        data_points = await self.analytics_repo.order_revenue_series(start=rng.start, end=rng.end, grouping=grouped_data, condition=PAID_ORDER_STATUSES)
        current_revenue = await self.analytics_repo.period_revenue(start=rng.start, end=rng.end, condition=PAID_ORDER_STATUSES)
        previous_revenue = await self.analytics_repo.period_revenue(start=rng.previous_start, end=rng.previous_end, condition=PAID_ORDER_STATUSES)
        
        response = {
            "grouping": grouped_data,
            "data_points": [{"date": r.bucket_date, "revenue": Decimal(r.revenue)} for r in data_points],
            "current_revenue": Decimal(current_revenue),
            "previous_revenue": Decimal(previous_revenue),
            "growth_percentage": safe_growth_pct(current_revenue, previous_revenue),
            "period_start": rng.start,
            "period_end": rng.end,
        }
        
        await set_analysis_cache(key, expire=settings.CACHE_TTL_REVENUE, value=response)

        return response


    # =============================================================================
    # 3. Order analytics
    # =============================================================================

    async def get_order_analytics(self, rng: ResolvedRange, grouped_data: Grouping) -> dict:
        
        grouped_data = grouping_for(rng, grouped_data)
        key = build_cache_key("orders", rng.label, grouped_data.value)
        
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response

        total, status_rows, series_rows = await self.analytics_repo.order_analysis(grouping=grouped_data, start=rng.start, end=rng.end)
        by_status = {
            status: 0 for status in
            ["pending", "processing", "shipped", "delivered", "cancelled", "confirmed"]
            }
        
        for status, count in status_rows:
            if status in by_status:
                by_status[status] = int(count)
                
        response = {
            "total": int(total),
            "by_status": by_status,
            "orders_over_time": [
                {"date": r.bucket_date, 
                 "order_count": int(r.order_count)
                } 
                for r in series_rows
            ],
            "grouping": grouped_data,
            "period_start": rng.start,
            "period_end": rng.end,
        }

        await set_analysis_cache(key, expire=settings.CACHE_TTL_ORDERS,value=response)
        
        return response


    # =============================================================================
    # 4. Product analytics
    # =============================================================================

    async def get_top_selling_or_revenue_products(self, rng: ResolvedRange, limit: int, sort_by: str) -> list[dict]:
        
        cache_prifix = "top-selling" if sort_by == "quantity" else "top-revenue"
        
        key = build_cache_key("products", cache_prifix, rng.label, str(limit))
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response
    
        rows = await self.analytics_repo.top_selling_or_revenue_product(
            start=rng.start, end=rng.end, 
            limit=limit, sort_by=sort_by, 
            condition=PAID_ORDER_STATUSES
            )
        
        response =  [
            {
                "product_id": r.id,
                "name": r.name,
                "quantity_sold": int(r.quantity_sold),
                "revenue": Decimal(r.revenue),
                "order_count": int(r.order_count),
            }
            for r in rows
        ]
        
        await set_analysis_cache(key, expire=settings.CACHE_TTL_TOP_PRODUCTS, value=response)
        
        return response


    async def get_lowest_selling_products(self, rng: ResolvedRange, limit: int) -> list[dict]:
        """
        Products that HAVE sold, ordered ascending by quantity — distinct from
        "zero sales" (below), which is products that never appear in an order at all.
        """
        key = build_cache_key("products", "lowest-selling", rng.label, str(limit))
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response
            
        rows = await self.analytics_repo.low_selling_product(
            start=rng.start, end=rng.end, 
            limit=limit, condition=PAID_ORDER_STATUSES
            )
        
        response = [
            {
                "product_id": r.id,
                "name": r.name,
                "quantity_sold": int(r.quantity_sold),
                "revenue": Decimal(r.revenue),
                "order_count": int(r.order_count),
            }for r in rows
                ]
        
        await set_analysis_cache(key, expire=settings.CACHE_TTL_TOP_PRODUCTS, value=response)
        
        return response


    # celery scheduler will also run this function every 10 minutes
    async def get_low_inventory_products(
        self, page: int = 1,
        page_size: int = 20,
        quantity: int | None = None,
        ) -> dict:
        
        quantity = quantity if quantity is not None else settings.LOW_STOCK_THRESHOLD
        
        skip = (page -1) * page_size
        
        low_product, count = await self.analytics_repo.low_inventory_stocks(offset=skip, limit=page_size, quantity=quantity)
        
        total_pages = ceil(count / page_size) if page_size is not None else 0
        
        return {
            "products": low_product, 
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages, 
            }
        
        
        
         
    async def get_zero_sales_products(self, rng: ResolvedRange) -> list[dict]:
        """
        Products with no paid order items in the window. Uses a correlated
        NOT EXISTS rather than fetching all order items into Python.
        """
        key = build_cache_key("products", "zero-sales", rng.label)
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response
            
        rows = await self.analytics_repo.zero_sales_product(start=rng.start, end=rng.end, condition=PAID_ORDER_STATUSES)
        
        response = [
            {
                "product_id": r.id, 
                "name": r.name, 
                "created_at": r.created_at
                } for r in rows
        ]

        await set_analysis_cache(key, expire=settings.CACHE_TTL_TOP_PRODUCTS, value=response)
                    
        return response

    # =============================================================================
    # 5. Customer analytics
    # =============================================================================

    async def get_customer_analytics(self, rng: ResolvedRange) -> dict:
        
        key = build_cache_key("customers", rng.label)
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response   
        
        (total_customers, new_customers, returning_customers,
         customers_with_purchase, customers_without_purchase, avg_spend
        ) = await self.analytics_repo.customer_analytics(start=rng.start, end=rng.end, condition=PAID_ORDER_STATUSES)
        
        response = {
            "total_customers": int(total_customers),
            "new_customers": int(new_customers),
            "returning_customers": int(returning_customers),
            "customers_with_purchase": int(customers_with_purchase),
            "customers_without_purchase": max(customers_without_purchase, 0),
            "average_customer_spending": Decimal(avg_spend).quantize(Decimal("0.01")),
            "period_start": rng.start,
            "period_end": rng.end,
        }
        
        await set_analysis_cache(key, expire=settings.CACHE_TTL_CUSTOMERS, value=response)

        return response


    async def _get_top_customers(self, rng: ResolvedRange, limit: int, order_by: str = "spending"
    ) -> list[dict]:

        rows = await self.analytics_repo.top_customers(
            start=rng.start, end=rng.end, 
            limit=limit, order_by=order_by, 
            condition=PAID_ORDER_STATUSES
            )
        
        return [
            {
                "customer_id": r.id,
                "email": r.email,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "order_count": int(r.order_count),
                "total_spent": Decimal(r.total_spent),
                "last_order_date": r.last_order_date,
            }
            for r in rows
        ]

    
    async def fetch_top_customers(self, rng: ResolvedRange, limit: int):
        
        key = build_cache_key("customers", "top", rng.label, str(limit))
        cache_response = await get_analysis_cache(key)
        if cache_response:
            return cache_response
        
        by_spending = await self._get_top_customers(rng, limit, order_by="spending")
        by_orders = await self._get_top_customers(rng, limit, order_by="orders")
        
        response = {"by_spending": by_spending, "by_order_count": by_orders}

        await set_analysis_cache(key, expire=settings.CACHE_TTL_CUSTOMERS, value=response)
        
        return response
    
    # =============================================================================
    # 6. Payment analytics 
    # =============================================================================

    async def get_payment_analytics(self, rng: ResolvedRange) -> dict | None:
        
        key = build_cache_key("payments", rng.label)
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response

        successful, failed, pending, cancelled, success_amt, refund_amt, total = await self.analytics_repo.payment_analysis(start=rng.start, end=rng.end)
        success_rate = round((int(successful) / int(total)) * 100, 2) if total else 0.0

        response = {
            "successful_payments": int(successful),
            "failed_payments": int(failed),
            "pending_payments": int(pending),
            "refunded_payments": int(cancelled),
            "total_successful_amount": Decimal(success_amt),
            "total_refunded_amount": Decimal(refund_amt),
            "success_rate": success_rate,
            "period_start": rng.start,
            "period_end": rng.end,
        }

        await set_analysis_cache(key, expire=settings.CACHE_TTL_PAYMENTS, value=response)
        
        return response

    # =============================================================================
    # 7. Period-over-period comparison
    # =============================================================================
    
    async def _period_comparison(self, start: datetime, end: datetime) -> dict:
        
        revenue, orders, aov, customers = await self.analytics_repo.period_comparison(
            start=start, end=end, condition=PAID_ORDER_STATUSES
            )
        return {
            "revenue": Decimal(revenue),
            "orders": int(orders),
            "average_order_value": Decimal(aov),
            "customers": int(customers),
        }

    
    async def get_period_comparison(self, rng: ResolvedRange) -> dict:
        
        key = build_cache_key("comparison", rng.label)
        cache_response = await get_analysis_cache(key)
        if cache_response is not None:
            return cache_response
        
        current = await self._period_comparison(start=rng.start, end=rng.end)
        previous = await self._period_comparison(start=rng.previous_start, end=rng.previous_end)
        
        response = {
            "revenue_growth_pct": safe_growth_pct(current["revenue"], previous["revenue"]),
            "order_growth_pct": safe_growth_pct(current["orders"], previous["orders"]),
            "customer_growth_pct": safe_growth_pct(current["customers"], previous["customers"]),
            "average_order_value_growth_pct": safe_growth_pct(
                current["average_order_value"], previous["average_order_value"]
            ),
            "current_period": current,
            "previous_period": previous,
        }
        
        await set_analysis_cache(key, expire=settings.CACHE_TTL_OVERVIEW, value=response)
        return response




