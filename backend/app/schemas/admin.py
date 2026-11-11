from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class FacilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    facility_type: Literal["hospital", "diagnostic"] | None = None
    address: str | None = Field(default=None, min_length=5)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    description: str | None = Field(default=None, max_length=2000)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError) as error:
                raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Fields cannot be null")
        return self


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    category: str | None = Field(default=None, min_length=2, max_length=100)
    service_type: Literal["doctor", "diagnostic"] | None = None
    provider_name: str | None = Field(default=None, max_length=180)
    fee_paise: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Fields cannot be null")
        return self


class UserAdminUpdate(BaseModel):
    is_active: bool | None = None
    role: Literal["patient", "facility_staff"] | None = None
    facility_id: int | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(
            getattr(self, field) is None
            for field in self.model_fields_set
            if field != "facility_id"
        ):
            raise ValueError("Fields cannot be null")
        if self.role == "patient" and self.facility_id is not None:
            raise ValueError("Patient accounts cannot be assigned to a facility")
        if "facility_id" in self.model_fields_set and self.role != "facility_staff":
            raise ValueError("A facility_id can only be set for a facility_staff account")
        return self


class AdminDashboardRead(BaseModel):
    facilities: int
    services: int
    bookings: int
    users: int | None


class AdminBookingRead(BaseModel):
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
    payment_collected_by_user_id: int | None
    payment_collector_name: str | None
    payment_reference: str | None
    status: str
    rejection_reason: str | None = None
    patient_name: str
    patient_email_masked: str
    facility_name: str
    service_name: str
    provider_name: str


class AdminUserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    facility_id: int | None
    facility_name: str | None = None
    is_active: bool
    email_verified: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
