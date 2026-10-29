from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if len(name) < 2:
            raise ValueError("Name must contain at least two non-space characters")
        return name

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
    development_otp: str | None = None


class EmailCodeRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    code: str = Field(pattern="^[0-9]{6}$")


class ResendVerificationRequest(BaseModel):
    email: EmailStr = Field(max_length=254)


class ResendVerificationResponse(BaseModel):
    message: str
    development_otp: str | None = None


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
    development_otp: str | None = None


class MessageResponse(BaseModel):
    message: str
