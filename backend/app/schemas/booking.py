from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class BookingCreate(BaseModel):
    facility_id: int
    service_id: int
    appointment_at: datetime
    payment_method: str = Field(pattern="^physical$")

class BookingRead(BaseModel):
    id: int
    facility_id: int
    service_id: int
    appointment_at: datetime
    payment_method: str
    payment_status: str
    status: str
    model_config = ConfigDict(from_attributes=True)

class BookingCreated(BookingRead):
    verification_code: str

class BookingSummary(BookingRead):
    facility_name: str
    service_name: str

class VerifyRequest(BaseModel):
    code: str = Field(pattern="^[0-9]{6}$")

class VerifyRead(BaseModel):
    valid: bool
    message: str
    booking_id: int | None = None
    payment_status: str | None = None
    appointment_at: datetime | None = None
