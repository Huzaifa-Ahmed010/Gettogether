from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class FacilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    facility_type: Literal["hospital", "diagnostic"] | None = None
    address: str | None = Field(default=None, min_length=5)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None

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
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Fields cannot be null")
        if self.role == "facility_staff" and self.facility_id is None:
            raise ValueError("Assigning facility staff requires a facility_id")
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
    status: str
    patient_name: str
    patient_email_masked: str
    facility_name: str
    service_name: str


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
