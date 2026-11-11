import calendar
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.models import Facility, FacilitySubscription, SubscriptionNotice, User

GRACE_PERIOD_DAYS = 7


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def add_billing_interval(value: datetime, interval: str) -> datetime:
    months = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(interval)
    if months is None:
        raise ValueError(f"Unsupported subscription billing interval: {interval}")
    utc_value = as_utc(value)
    month_index = utc_value.month - 1 + months
    year = utc_value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(utc_value.day, calendar.monthrange(year, month)[1])
    return utc_value.replace(year=year, month=month, day=day)


def effective_subscription_status(
    subscription: FacilitySubscription | None,
    now: datetime | None = None,
) -> str:
    if subscription is None:
        return "unsubscribed"
    if subscription.status in {"pending_payment", "cancelled", "suspended"}:
        return subscription.status
    now = as_utc(now or datetime.now(timezone.utc))
    period_end = subscription.current_period_end
    grace_end = subscription.grace_period_end
    if period_end is None or grace_end is None:
        return subscription.status
    if now < as_utc(period_end):
        return "active"
    if now <= as_utc(grace_end):
        return "grace_period"
    return "expired"


def facility_accepts_requests(db: Session, facility_id: int) -> bool:
    facility = db.get(Facility, facility_id)
    if facility is None or not facility.is_active:
        return False
    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.facility_id == facility_id)
        .first()
    )
    return effective_subscription_status(subscription) in {"active", "grace_period"}


def require_facility_entitlement(
    db: Session,
    facility_id: int,
    *,
    operational_write: bool,
) -> Facility:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    if not operational_write:
        return facility
    if not facility.is_active:
        raise HTTPException(403, "This facility is not active on the platform")
    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.facility_id == facility_id)
        .first()
    )
    state = effective_subscription_status(subscription)
    if state not in {"active", "grace_period"}:
        raise HTTPException(403, "An active facility subscription is required for this operation")
    return facility


def require_staff_facility(
    db: Session,
    user: User,
    facility_id: int | None = None,
    *,
    operational_write: bool = False,
) -> Facility:
    if user.role != "facility_staff" or user.facility_id is None:
        raise HTTPException(403, "Facility staff access is required")
    if facility_id is not None and user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to access this facility")
    return require_facility_entitlement(
        db,
        user.facility_id,
        operational_write=operational_write,
    )


def record_subscription_notice(
    db: Session,
    subscription: FacilitySubscription,
    event_key: str,
    event_type: str,
    message: str,
) -> None:
    existing = (
        db.query(SubscriptionNotice.id)
        .filter(
            SubscriptionNotice.subscription_id == subscription.id,
            SubscriptionNotice.event_key == event_key,
        )
        .first()
    )
    if existing is None:
        db.add(
            SubscriptionNotice(
                facility_id=subscription.facility_id,
                subscription_id=subscription.id,
                event_key=event_key,
                event_type=event_type,
                message=message,
            )
        )


def refresh_subscription_state(
    db: Session,
    subscription: FacilitySubscription,
    now: datetime,
) -> str:
    state = effective_subscription_status(subscription, now)
    if state != subscription.status:
        subscription.status = state
        record_audit_event(
            db,
            None,
            f"subscription.{state}",
            "facility_subscription",
            subscription.id,
        )
        if state in {"grace_period", "expired"}:
            record_subscription_notice(
                db,
                subscription,
                f"state:{state}",
                state,
                "Your facility subscription entered its grace period."
                if state == "grace_period"
                else "Your facility subscription has expired. Billing and permitted history remain available.",
            )
    period_end = subscription.current_period_end
    grace_end = subscription.grace_period_end
    if period_end is not None and subscription.status == "active":
        remaining = as_utc(period_end) - as_utc(now)
        if timedelta(0) < remaining <= timedelta(days=3):
            record_subscription_notice(
                db,
                subscription,
                "renewal:3-days",
                "renewal_reminder",
                "Your facility subscription period ends within three days.",
            )
        elif timedelta(days=3) < remaining <= timedelta(days=7):
            record_subscription_notice(
                db,
                subscription,
                "renewal:7-days",
                "renewal_reminder",
                "Your facility subscription period ends within seven days.",
            )
    if grace_end is not None and subscription.status == "grace_period":
        remaining = as_utc(grace_end) - as_utc(now)
        if timedelta(0) < remaining <= timedelta(days=3):
            record_subscription_notice(
                db,
                subscription,
                "grace:3-days",
                "grace_reminder",
                "Your facility subscription grace period ends within three days.",
            )
    return state
