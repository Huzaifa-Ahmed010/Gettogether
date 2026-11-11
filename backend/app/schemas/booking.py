from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class BookingCreate(BaseModel):
    facility_id: int
    service_id: int
    appointment_at: datetime
    payment_method: str = Field(pattern="^physical$")

    @field_validator("appointment_at")
    @classmethod
    def require_aware_appointment_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("appointment_at must include a UTC offset or timezone")
        return value.astimezone(timezone.utc)


class BookingRead(BaseModel):
    id: int
    facility_id: int
    service_id: int
    appointment_at: datetime
    payment_method: str
    payment_status: str
    payment_due_paise: int
    payment_amount_paise: int | None
    payment_currency: str
    payment_collected_at: datetime | None
    payment_reference: str | None
    status: str
    rejection_reason: str | None = None
    model_config = ConfigDict(from_attributes=True)

class BookingCreated(BookingRead):
    pass

class BookingSummary(BookingRead):
    facility_name: str
    service_name: str
    provider_name: str

class BookingDocumentRead(BaseModel):
    id: int
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)

class VerifyRequest(BaseModel):
    code: str = Field(pattern="^[0-9]{6}$")

class PaymentCollectionRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=120)

    @field_validator("reference")
    @classmethod
    def normalize_reference(cls, value: str) -> str:
        reference = value.strip()
        if not reference:
            raise ValueError("A receipt or payment reference is required")
        return reference

class VerifyRead(BaseModel):
    valid: bool
    message: str
    booking_id: int | None = None
    payment_status: str | None = None
    appointment_at: datetime | None = None


class BookingDecisionRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        reason = value.strip()
        if len(reason) < 5:
            raise ValueError("A clear rejection reason is required")
        return reason


class BookingCheckInCode(BaseModel):
    verification_code: str = Field(pattern="^[0-9]{6}$")
