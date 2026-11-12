from pydantic import EmailStr, Field, field_validator

from app.shared.schema import LoweredStripedSchema, SharedResponseSchema, StripedSchema
from app.shared.utility import format_strings, validate_password


class CreateUser(StripedSchema):
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, email: str):
        return format_strings(email)
    
    @field_validator("password", mode="before")
    @classmethod
    def validate(cls, password: str):
        return validate_password(password)


class TokenResponse(SharedResponseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(StripedSchema):
    refresh_token: str


class ChangePassword(StripedSchema):
    old_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)
    
    @field_validator("new_password", mode="before")
    @classmethod
    def validate(cls, new_password: str):
        return validate_password(new_password)


class EmailVerification(LoweredStripedSchema):
    email: EmailStr
    


class OTPVerify(StripedSchema):
    email: EmailStr
    otp: str
    
    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, email: str):
        return format_strings(email)


class PasswordReset(StripedSchema):
    reset_token: str
    new_password: str = Field(..., min_length=8)
    
    @field_validator("new_password", mode="before")
    @classmethod
    def validate(cls, new_password: str):
        return validate_password(new_password)

