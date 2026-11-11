from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

class FacilityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    facility_type: str = Field(pattern="^(hospital|diagnostic)$")
    address: str = Field(min_length=5)
    city: str = Field(min_length=2, max_length=100)
    phone: str = ""
    description: str = Field(default="", max_length=2000)
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

class FacilityRead(FacilityCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    category: str = Field(min_length=2, max_length=100)
    service_type: str = Field(pattern="^(doctor|diagnostic)$")
    provider_name: str = ""
    fee_paise: int = Field(ge=0, description="Fee in paise (INR × 100)")

class ServiceRead(ServiceCreate):
    id: int
    facility_id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class ServiceSearchRead(ServiceRead):
    facility_name: str
    facility_city: str
    facility_address: str
    facility_phone: str
