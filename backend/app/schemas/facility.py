from pydantic import BaseModel, ConfigDict, Field

class FacilityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    facility_type: str = Field(pattern="^(hospital|diagnostic)$")
    address: str = Field(min_length=5)
    city: str = Field(min_length=2, max_length=100)
    phone: str = ""

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
