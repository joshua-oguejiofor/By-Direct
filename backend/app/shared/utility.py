import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from bleach import clean
from sqlalchemy import func, literal

from app.core.config import settings
from app.core.enums import Grouping
from app.depends.analitics_depends import ResolvedRange
from app.models import Product, User


def validate_phone_number(contact_number: str):
    # Regex pattern allowing only digits (starts with 234 or 0, followed by 7, 8, or 9, then 9 more digits)
    
    if contact_number is None:
        return None
    
    cleaned_input = str(contact_number).strip()
    pattern = r"(?:\+?234|0)([7-9][0-9]{9})"
    
    match = re.fullmatch(pattern, cleaned_input)
    if not match:
        raise ValueError("Invalid phone number format")
    
    # Extract the 10-digit customer number (e.g. [234|0], [8031234567])
    phone = match.group(1)
        
    # append +234 to get the final international format
    return  f"+234{phone}"
    
    
def sanitize_input(value: str) -> str:
    
    if value is None:
        return None
    
    return clean(value)


# This strips all white space and convert string datatype to lower case
def format_strings(value: str):
    
    if value is None:
        return None
    
    if isinstance(value, str): # avoid error when it meets other datatype
        return value.strip().lower()
    return value

def validate_password(password: str) -> str:
    
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[+_@,-]).{8,}$" # the ^ and $ set the start and end
    
    if not re.fullmatch(pattern, password):
        raise ValueError("Password must be at least 8 characters long and include upper, lower, digit, and special characters (+, -, _, @, ,).")
    return password


def validate_name(name: str) -> str:
    
    if name is None:
        return None
    
    pattern = r"[A-Za-z]+"
    
    if not re.fullmatch(pattern, name):
        raise ValueError(f"Field support only alphabets, you entered {name}")
    return name.strip().lower()


def admin_check(current_user: User | None) -> bool:
    return ( 
        False if current_user is None 
        else bool(current_user.role in settings.ADMINS)
        )
            
# shared helper to get the current price (discount if avaliable)
def optimize_prize(product: Product):
    price = product.discount_price if product.discount_price else product.price
    return price
    
    
def get_frontend_redirect_url(msg: str, prifix: str) -> str:
    
    base_url = f"{settings.FRONTEND_URL}{prifix}"
    query_params = {"msg": msg}
    return f"{base_url}?{urlencode(query_params)}"

# =============================================================================
# Shared helpers for Analytics
# =============================================================================

def grouping_for(rng: ResolvedRange, override: Grouping | None) -> Grouping:
    return override if override is not None else rng.grouping


def build_cache_key(*parts: str) -> str:
    """
    e.g. build_cache_key("overview", "30d") -> "analytics:overview:30d"
    Always include every filter that changes the result, so one admin's
    filtered view can never be served to another admin's differently
    filtered request.
    """
    return ":".join([*parts])
    


def default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return {"__decimal__": str(obj)}
    if isinstance(obj, datetime):
        return {"__datetime__": obj.isoformat()}
    if isinstance(obj, date):
        return {"__date__": obj.isoformat()}
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def object_hook(d: dict) -> Any:
    if "__decimal__" in d:
        return Decimal(d["__decimal__"])
    if "__datetime__" in d:
        return datetime.fromisoformat(d["__datetime__"])
    if "__date__" in d:
        return date.fromisoformat(d["__date__"])
    return d


def safe_growth_pct(current: Decimal | float, previous: Decimal | float) -> float:
    """percentage_change = ((current - previous) / previous) * 100, div-by-zero safe."""
    current = float(current)
    previous = float(previous)
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)



def date_bucket_expr(column, grouping: Grouping):
    """
    Returns a date-bucketing SQL expression usable in both SELECT and
    GROUP BY. `func.date()` (not CAST(... AS DATE)) is used for the DAY case
    because it behaves identically as a plain "YYYY-MM-DD" string on both
    MySQL and SQLite (CAST AS DATE is not portable across the two, which
    matters for the SQLite-backed unit tests in this deliverable).
    """
    if grouping == Grouping.DAY:
        return func.date(column)
    if grouping == Grouping.WEEK:
        # Monday of the ISO week containing `column`.
        return func.str_to_date(
            func.concat(func.yearweek(column, 3), literal(" Monday")), literal("%X%V %W")
        )
    if grouping == Grouping.MONTH:
        return func.date_format(column, literal("%Y-%m-01"))
    raise ValueError(f"Unsupported grouping: {grouping}")
