from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.audit import record_audit_event
from app.core.config import settings
from app.core.razorpay import PaymentGatewayError, create_order, gateway_is_configured
from app.db.session import get_db
from app.models import (
    Facility,
    FacilitySubscription,
    SubscriptionNotice,
    SubscriptionPayment,
    SubscriptionPlan,
    User,
)
from app.schemas.subscription import (
    CheckoutRead,
    CheckoutRequest,
    FacilitySubscriptionRead,
    SubscriptionPaymentRead,
    SubscriptionPlanRead,
)
from app.services.subscriptions import (
    effective_subscription_status,
    refresh_subscription_state,
    require_staff_facility,
)

router = APIRouter(prefix="/facility/subscription", tags=["facility-subscription"])


def _subscription_response(
    db: Session,
    facility: Facility,
    subscription: FacilitySubscription | None,
) -> FacilitySubscriptionRead:
    plan = db.get(SubscriptionPlan, subscription.plan_id) if subscription and subscription.plan_id else None
    payments = (
        db.query(SubscriptionPayment)
        .filter(SubscriptionPayment.facility_id == facility.id)
        .order_by(SubscriptionPayment.created_at.desc(), SubscriptionPayment.id.desc())
        .limit(50)
        .all()
    )
    notices = (
        db.query(SubscriptionNotice)
        .filter(SubscriptionNotice.facility_id == facility.id)
        .order_by(SubscriptionNotice.created_at.desc(), SubscriptionNotice.id.desc())
        .limit(20)
        .all()
    )
    return FacilitySubscriptionRead(
        id=subscription.id if subscription else None,
        facility_id=facility.id,
        facility_name=facility.name,
        status=effective_subscription_status(subscription),
        plan_id=subscription.plan_id if subscription else None,
        plan_name=(
            subscription.plan_name_snapshot
            if subscription and subscription.plan_name_snapshot
            else (plan.name if plan else None)
        ),
        billing_interval=(
            subscription.billing_interval_snapshot
            if subscription and subscription.billing_interval_snapshot
            else (plan.billing_interval if plan else None)
        ),
        price_paise=(
            subscription.price_paise_snapshot
            if subscription and subscription.price_paise_snapshot is not None
            else (plan.price_paise if plan else None)
        ),
        currency=subscription.currency_snapshot if subscription else "INR",
        current_period_start=subscription.current_period_start if subscription else None,
        current_period_end=subscription.current_period_end if subscription else None,
        grace_period_end=subscription.grace_period_end if subscription else None,
        owner_user_id=facility.owner_user_id,
        cancel_at_period_end=subscription.cancel_at_period_end if subscription else False,
        payments=[SubscriptionPaymentRead.model_validate(payment) for payment in payments],
        notices=[notice.message for notice in notices],
    )


@router.get("/plans", response_model=list[SubscriptionPlanRead])
def list_available_subscription_plans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "facility_staff":
        raise HTTPException(403, "Facility staff access is required")
    return (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.billing_interval, SubscriptionPlan.id)
        .all()
    )


@router.get("", response_model=FacilitySubscriptionRead)
def get_facility_subscription(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    facility = require_staff_facility(db, user)
    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.facility_id == facility.id)
        .first()
    )
    if subscription is not None:
        refresh_subscription_state(db, subscription, datetime.now(timezone.utc))
        db.commit()
    return _subscription_response(db, facility, subscription)


def _create_subscription_checkout(
    payload: CheckoutRequest,
    db: Session,
    user: User,
):
    facility = require_staff_facility(db, user)
    if facility.owner_user_id != user.id:
        raise HTTPException(403, "Only the facility billing owner can initiate subscription payments")
    if not gateway_is_configured():
        raise HTTPException(503, "Online subscription billing is not configured yet")
    plan = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.id == payload.plan_id, SubscriptionPlan.is_active.is_(True))
        .first()
    )
    if plan is None:
        raise HTTPException(404, "Active subscription plan not found")
    if plan.price_paise is None or plan.price_paise <= 0:
        raise HTTPException(409, "This plan is not available for purchase until its price is configured")

    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.facility_id == facility.id)
        .with_for_update()
        .first()
    )
    now = datetime.now(timezone.utc)
    if subscription is None:
        subscription = FacilitySubscription(
            facility_id=facility.id,
            billing_contact_user_id=user.id,
            status="pending_payment",
        )
        db.add(subscription)
        db.flush()
    payment = SubscriptionPayment(
        facility_id=facility.id,
        subscription_id=subscription.id,
        plan_id=plan.id,
        amount_paise=plan.price_paise,
        currency=plan.currency,
        plan_name_snapshot=plan.name,
        billing_interval_snapshot=plan.billing_interval,
        status="created",
    )
    db.add(payment)
    db.flush()
    record_audit_event(db, user, "subscription.checkout_created", "subscription_payment", payment.id)
    db.commit()
    db.refresh(payment)

    try:
        order_id = create_order(
            amount_paise=payment.amount_paise,
            currency=payment.currency,
            receipt=f"subscription-{payment.id}",
            subscription_id=subscription.id,
        )
    except PaymentGatewayError as error:
        payment.status = "failed"
        payment.failure_reason = str(error)[:300]
        record_audit_event(
            db,
            user,
            "subscription.checkout_failed",
            "subscription_payment",
            payment.id,
        )
        db.commit()
        raise HTTPException(502, str(error)) from error

    payment.gateway_order_id = order_id
    payment.status = "pending"
    payment.updated_at = now
    db.commit()
    return CheckoutRead(
        payment_id=payment.id,
        order_id=order_id,
        amount_paise=payment.amount_paise,
        currency=payment.currency,
        key_id=settings.razorpay_key_id,
        facility_name=facility.name,
        plan_name=plan.name,
        description=f"{plan.name} facility subscription",
        prefill_email=user.email,
    )


@router.post("/checkout", response_model=CheckoutRead, status_code=201)
def create_subscription_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create_subscription_checkout(payload, db, user)


@router.post("/renew", response_model=CheckoutRead, status_code=201)
def renew_facility_subscription(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create_subscription_checkout(payload, db, user)
