import re
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    # Automatically generate __tablename__ in lowercase from class name
    # e.g., User -> users, OrderItem -> order_items
    @declared_attr.directive
    def __tablename__(cls) -> str:
        # Converts PascalCase to snake_case (e.g. OrderItem -> order_item)
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return f"{name}s"
    

class TimestampMixin:
    """Mixin to add audit timestamp columns to models."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False,
        server_default=sa.func.now()
    )
    

class UpdateTimestampMixin:
    """Update mixin to add audit timestamp columns to models."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        server_onupdate=sa.func.now(),
        nullable=False,
    )
    
    
    