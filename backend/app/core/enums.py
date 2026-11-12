from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    SUPERADMIN = "super_admin"
    CUSTOMER = "customer"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    CONFIRMED = "confirmed"
    

class PaymentStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    
class PaymentProvider(StrEnum):
    STRIPE = "stripe"
    PAYSTACK = "paystack"
    
    
class Period(StrEnum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    PREVIOUS_MONTH = "previous_month"
    THIS_YEAR = "this_year"
    CUSTOM = "custom"


class Grouping(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
