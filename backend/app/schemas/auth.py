from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=24)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if len(name) < 2:
            raise ValueError("Name must contain at least two non-space characters")
        return name

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Enter a valid phone number in international format")
        if not value.strip():
            return None
        phone = re.sub(r"[\s().-]", "", value)
        if re.fullmatch(r"[6-9]\d{9}", phone):
            phone = f"+91{phone}"
        if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
            raise ValueError("Enter a valid phone number in international format")
        return phone

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value.strip()) < 12:
            raise ValueError("Password must contain at least 12 non-space characters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: datetime
    role: str
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class VerificationPendingResponse(BaseModel):
    message: str
    email: EmailStr


class EmailCodeRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    code: str = Field(pattern="^[0-9]{6}$")


class ResendVerificationRequest(BaseModel):
    email: EmailStr = Field(max_length=254)


class ResendVerificationResponse(BaseModel):
    message: str


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(max_length=254)


class PasswordResetCompleteRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    code: str = Field(pattern="^[0-9]{6}$")
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value.strip()) < 12:
            raise ValueError("Password must contain at least 12 non-space characters")
        return value


class PasswordResetResponse(BaseModel):
    message: str


class MessageResponse(BaseModel):
    message: str
