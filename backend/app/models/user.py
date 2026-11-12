from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole

from .base import Base, UpdateTimestampMixin


class User(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True,nullable=False,index=True,)
    hashed_password: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(sa.Enum(UserRole, values_callable=lambda enum_class: [item.value for item in enum_class]), nullable=False, default=UserRole.CUSTOMER)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)

    # 1-to-1 Relationships
    profile: Mapped["Profile"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    cart: Mapped["Cart"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False) # type: ignore # noqa: F821
    wishlist: Mapped["Wishlist"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False) # noqa: F821 # type: ignore

    # 1-to-Many Collections
    orders: Mapped[list["Order"]] = relationship(back_populates="user")  # type: ignore # noqa: F821
    reviews: Mapped[list["Review"]] = relationship(back_populates="user") # noqa: F821 # type: ignore


class Profile(Base, UpdateTimestampMixin):

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, default=None)
    last_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, default=None)
    phone_number: Mapped[str] = mapped_column(sa.String(30), nullable=False, default=None, unique=True)
    address: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    country: Mapped[str] = mapped_column(sa.String(100), nullable=False, server_default="nigeria")

    
    # Reverse 1-to-1
    user: Mapped["User"] = relationship(back_populates="profile")
    
    
    

    