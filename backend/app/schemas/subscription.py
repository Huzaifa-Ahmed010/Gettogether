from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BillingInterval = Literal["monthly", "quarterly", "yearly"]


class SubscriptionPlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    billing_interval: BillingInterval
    price_paise: int | None = Field(default=None, ge=1)
    currency: Literal["INR"] = "INR"
    is_active: bool = False

    @model_validator(mode="after")
    def require_price_for_active_plan(self):
        if self.is_active and self.price_paise is None:
            raise ValueError("Set a plan price before activating it")
        return self


class SubscriptionPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    billing_interval: BillingInterval | None = None
    price_paise: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class SubscriptionPlanRead(BaseModel):
    id: int
    name: str
    description: str
    billing_interval: BillingInterval
    price_paise: int | None
    currency: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class SubscriptionPaymentRead(BaseModel):
    id: int
    gateway: str
    gateway_order_id: str | None
    amount_paise: int
    currency: str
    plan_name_snapshot: str
    billing_interval_snapshot: str
    status: str
    paid_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FacilitySubscriptionRead(BaseModel):
    id: int | None
    facility_id: int
    facility_name: str
    status: str
    plan_id: int | None
    plan_name: str | None
    billing_interval: str | None
    price_paise: int | None
    currency: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    grace_period_end: datetime | None
    owner_user_id: int | None
    cancel_at_period_end: bool
    payments: list[SubscriptionPaymentRead] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class CheckoutRequest(BaseModel):
    plan_id: int = Field(gt=0)


class CheckoutRead(BaseModel):
    payment_id: int
    order_id: str
    amount_paise: int
    currency: str
    key_id: str
    facility_name: str
    plan_name: str
    description: str
    prefill_email: str


class AdminSubscriptionExtension(BaseModel):
    days: int = Field(ge=1, le=365)
    reason: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 5:
            raise ValueError("A clear reason is required")
        return self


class FacilityOwnerUpdate(BaseModel):
    user_id: int = Field(gt=0)


class AdminSubscriptionPaymentRead(SubscriptionPaymentRead):
    facility_id: int
    facility_name: str


class PlatformSubscriptionRead(BaseModel):
    id: int
    facility_id: int
    facility_name: str
    facility_active: bool
    status: str
    plan_name: str | None
    billing_interval: str | None
    price_paise: int | None
    currency: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    grace_period_end: datetime | None
    owner_user_id: int | None


class AuditEventRead(BaseModel):
    id: int
    actor_user_id: int | None
    action: str
    resource_type: str
    resource_id: int | None
    details: str | None
    created_at: datetime


class PaymentWebhookEventRead(BaseModel):
    id: int
    gateway_event_id: str
    gateway: str
    event_type: str
    payload_sha256: str
    processing_status: str
    received_at: datetime
    processed_at: datetime | None
