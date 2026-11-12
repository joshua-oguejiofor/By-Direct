from datetime import date, datetime
from decimal import Decimal

from app.core.enums import Grouping
from app.shared.schema import SharedResponseSchema

# ---------------------------------------------------------------- Overview

class AnalyticsOverviewResponse(SharedResponseSchema):
    total_revenue: Decimal
    total_orders: int
    total_customers: int
    total_products: int
    average_order_value: Decimal
    total_items_sold: int
    pending_orders: int
    delivered_orders: int
    cancelled_orders: int
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------- Revenue

class _RevenueDataPoint(SharedResponseSchema):
    date: date
    revenue: Decimal


class RevenueAnalyticsResponse(SharedResponseSchema):
    grouping: Grouping
    data_points: list[_RevenueDataPoint]
    current_revenue: Decimal
    previous_revenue: Decimal
    growth_percentage: float
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------- Orders

class _OrdersByStatus(SharedResponseSchema):
    pending: int = 0
    processing: int = 0
    shipped: int = 0
    delivered: int = 0
    cancelled: int = 0
    confirmed: int = 0


class _OrderTimeSeriesPoint(SharedResponseSchema):
    date: date
    order_count: int


class OrderAnalyticsResponse(SharedResponseSchema):
    total: int
    by_status: _OrdersByStatus
    orders_over_time: list[_OrderTimeSeriesPoint]
    grouping: Grouping
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------- Products

class TopProductResponse(SharedResponseSchema):
    product_id: int
    name: str
    quantity_sold: int
    revenue: Decimal
    order_count: int


class ZeroSalesProductResponse(SharedResponseSchema):
    product_id: int
    name: str
    created_at: datetime


# ---------------------------------------------------------------- Customers

class _TopCustomerResponse(SharedResponseSchema):
    customer_id: int
    email: str
    first_name: str | None
    last_name: str | None
    order_count: int
    total_spent: Decimal
    last_order_date: datetime | None


class CustomerAnalyticsResponse(SharedResponseSchema):
    total_customers: int
    new_customers: int
    returning_customers: int
    customers_with_purchase: int
    customers_without_purchase: int
    average_customer_spending: Decimal
    period_start: datetime
    period_end: datetime


class TopCustomersListResponse(SharedResponseSchema):
    by_spending: list[_TopCustomerResponse]
    by_order_count: list[_TopCustomerResponse]


# ---------------------------------------------------------------- Payments

class PaymentAnalyticsResponse(SharedResponseSchema):
    successful_payments: int
    failed_payments: int
    pending_payments: int
    refunded_payments: int
    total_successful_amount: Decimal
    total_refunded_amount: Decimal
    success_rate: float
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------- Comparison

class PeriodComparisonResponse(SharedResponseSchema):
    revenue_growth_pct: float
    order_growth_pct: float
    customer_growth_pct: float
    average_order_value_growth_pct: float
    current_period: dict
    previous_period: dict


# ---------------------------------------------------------------- Errors



class _AlalyticsProductImageResponse(SharedResponseSchema):
    id: int
    url: str
    alt_text: str | None
    is_primary: bool

class _AnalyticsProductResponse(SharedResponseSchema):
    id: int
    name: str
    slug: str
    category_id: int
    description: str | None
    price: Decimal
    discount_price: Decimal | None
    stock_quantity: int
    brand: str | None
    average_rating: float
    total_reviews: int
    is_active: bool
    is_featured: bool
    images: list[_AlalyticsProductImageResponse]
    created_at: datetime
    updated_at: datetime

    
class LowstockResponse(SharedResponseSchema):
    products: list[_AnalyticsProductResponse]
    count: int
    page: int
    page_size: int
    total_pages: int 
