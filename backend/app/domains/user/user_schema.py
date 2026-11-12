from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.shared.schema import SharedResponseSchema, StripedSchema
from app.shared.utility import format_strings, validate_name, validate_phone_number


class UserProfile(StripedSchema):
    """Will add re format to validate phone number"""
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone_number: str = Field(...)
    address: str | None = None
    city: str | None = None
    country: str
    
    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate(cls, name: str):
        return validate_name(name)
    
    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone(cls, phone_number: str): 
        return validate_phone_number(phone_number)
    
    @field_validator("address", "city", "country", mode="before")
    @classmethod
    def validate_field(cls, value: str):
        return format_strings(value)
    

class UpdateProfile(StripedSchema):
    first_name: str | None = Field(None, min_length=2, max_length=100)
    last_name: str | None = Field(None, min_length=2, max_length=100)
    phone_number: str | None = Field(None)
    address: str | None = None
    city: str | None = None
    country: str | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate(cls, name: str):
        return validate_name(name)
    
    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone(cls, phone_number: str): 
        return validate_phone_number(phone_number)
    
    @field_validator("address", "city", "country", mode="before")
    @classmethod
    def validate_field(cls, value: str):
        return format_strings(value)
    

class _UserResponse(SharedResponseSchema):
    id: int
    email: str
    role: str
    is_active: bool
    is_verified: bool | None
    deleted_at: datetime | None
    is_deleted: bool
    created_at: datetime


class ProfileResponse(SharedResponseSchema):
    user: _UserResponse
    id: int
    first_name: str
    last_name: str
    phone_number: str
    address: str | None
    city: str | None
    country: str
    created_at: datetime
    updated_at: datetime | None

class UserListResponse(SharedResponseSchema):
    users: list[ProfileResponse]
    count: int
    page: int
    page_size: int
    total_pages: int

