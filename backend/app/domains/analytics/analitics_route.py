from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.enums import Grouping
from app.depends.analitics_depends import (
    ResolvedRange,
    get_date_range,
    get_grouping_override,
)
from app.depends.current_user import get_admins
from app.depends.di_injection import get_analytics_service

from .analytics_schema import (
    AnalyticsOverviewResponse,
    CustomerAnalyticsResponse,
    LowstockResponse,
    OrderAnalyticsResponse,
    PaymentAnalyticsResponse,
    PeriodComparisonResponse,
    RevenueAnalyticsResponse,
    TopCustomersListResponse,
    TopProductResponse,
    ZeroSalesProductResponse,
)
from .analytics_service import AnaliticsService

router = APIRouter(dependencies=[Depends(get_admins)])




resolve_range = Annotated[ResolvedRange, Depends(get_date_range)]
analytics_service_ = Annotated[AnaliticsService, Depends(get_analytics_service)]
group_overide = Annotated[Grouping | None, Depends(get_grouping_override)]
# ---------------------------------------------------------------- Overview

@router.get("/overview", response_model=AnalyticsOverviewResponse, status_code=200)
async def analytics_overview(
    rng: resolve_range,
    service: analytics_service_,
):
    
    return await service.get_overview(rng)


# ---------------------------------------------------------------- Revenue

@router.get("/revenue", response_model=RevenueAnalyticsResponse, status_code=200)
async def analytics_revenue(
    rng: resolve_range,
    service: analytics_service_,
    group_by: group_overide,
):
    
    return await service.get_revenue_analytics(rng=rng, grouped_data=group_by)



@router.get("/inventory", response_model=LowstockResponse, status_code=200)
async def get_low_stock(
    service: analytics_service_,
    quantity: int = Query(ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    ):
    """Admin only. List all products with stock at or below 5 units for inventory restocking alerts."""
    return await service.get_low_inventory_products(quantity=quantity, page=page, page_size=page_size)

# ---------------------------------------------------------------- Orders

@router.get("/orders", response_model=OrderAnalyticsResponse, status_code=200)
async def analytics_orders(
    rng: resolve_range,
    service: analytics_service_,
    group_by: group_overide,
):
    
    return await service.get_order_analytics(rng=rng, grouped_data=group_by)


# ---------------------------------------------------------------- Products

@router.get("/products/top-selling", response_model=list[TopProductResponse], status_code=200)
async def top_selling_products(
    rng: resolve_range,
    service: analytics_service_,
    limit: int = Query(10, ge=1, le=50),
):
    return await service.get_top_selling_or_revenue_products(rng=rng, limit=limit, sort_by="quantity")


@router.get("/products/top-revenue", response_model=list[TopProductResponse], status_code=200)
async def top_revenue_products(
    rng: resolve_range,
    service: analytics_service_,
    limit: int = Query(10, ge=1, le=50),
):
    
    return await service.get_top_selling_or_revenue_products(rng, limit, sort_by="revenue")
    

@router.get("/products/lowest-selling", response_model=list[TopProductResponse], status_code=200)
async def lowest_selling_products(
    rng: resolve_range,
    service: analytics_service_,
    limit: int = Query(10, ge=1, le=50),
):
    
    return await service.get_lowest_selling_products(rng, limit)
        

@router.get("/products/zero-sales", response_model=list[ZeroSalesProductResponse], status_code=200)
async def zero_sales_products(
    rng: resolve_range,
    service: analytics_service_,
):
    
    return await service.get_zero_sales_products(rng)

# ---------------------------------------------------------------- Customers

@router.get("/customers", response_model=CustomerAnalyticsResponse, status_code=200)
async def analytics_customers(
    rng: resolve_range,
    service: analytics_service_,
):
    
    return await service.get_customer_analytics(rng)


@router.get("/customers/top", response_model=TopCustomersListResponse, status_code=200)
async def top_customers(
    rng: resolve_range,
    service: analytics_service_,
    limit: int = Query(10, ge=1, le=50),
):
    
    return await service.fetch_top_customers(rng=rng, limit=limit)


# ---------------------------------------------------------------- Payments

@router.get("/payments", response_model=PaymentAnalyticsResponse, status_code=200)
async def analytics_payments(
    rng: resolve_range,
    service: analytics_service_,
):
    
    return await service.get_payment_analytics(rng)

# ---------------------------------------------------------------- Comparison

@router.get("/comparison", response_model=PeriodComparisonResponse, status_code=200)
async def period_comparison(
    rng: resolve_range,
    service: analytics_service_,
):
    
    return await service.get_period_comparison(rng)
