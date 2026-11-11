import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.razorpay import verify_webhook_signature
from app.db.session import get_db
from app.models import (
    Facility,
    FacilitySubscription,
    PaymentWebhookEvent,
    SubscriptionPayment,
)
from app.services.subscriptions import (
    GRACE_PERIOD_DAYS,
    add_billing_interval,
    as_utc,
    record_subscription_notice,
)

router = APIRouter(prefix="/webhooks", tags=["payment-webhooks"])


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str = Header(default="", alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str = Header(default="", alias="X-Razorpay-Event-Id"),
):
    body = await request.body()
    if not verify_webhook_signature(body, x_razorpay_signature):
        raise HTTPException(400, "Invalid payment webhook signature")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(400, "Invalid payment webhook payload") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
        raise HTTPException(400, "Invalid payment webhook payload")

    event_type = payload["event"][:80]
    payload_hash = hashlib.sha256(body).hexdigest()
    event_id = x_razorpay_event_id.strip()
    if not event_id or len(event_id) > 120:
        event_id = f"sha256:{payload_hash}"
    if (
        db.query(PaymentWebhookEvent.id)
        .filter(PaymentWebhookEvent.gateway_event_id == event_id)
        .first()
    ):
        return {"status": "duplicate"}

    if event_type not in {"payment.captured", "payment.failed"}:
        db.add(
            PaymentWebhookEvent(
                gateway_event_id=event_id,
                gateway="razorpay",
                event_type=event_type,
                payload_sha256=payload_hash,
                processing_status="ignored",
                processed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return {"status": "ignored"}

    event_payload = payload.get("payload")
    payment_payload = event_payload.get("payment") if isinstance(event_payload, dict) else None
    entity = payment_payload.get("entity") if isinstance(payment_payload, dict) else None
    if not isinstance(entity, dict):
        raise HTTPException(400, "Payment webhook is missing the payment details")
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    amount = entity.get("amount")
    currency = entity.get("currency")
    if (
        not isinstance(order_id, str)
        or not isinstance(payment_id, str)
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or not isinstance(currency, str)
    ):
        raise HTTPException(400, "Payment webhook contains invalid payment details")
    payment = (
        db.query(SubscriptionPayment)
        .filter(SubscriptionPayment.gateway_order_id == order_id)
        .with_for_update()
        .first()
    )
    if payment is None:
        raise HTTPException(404, "Payment order not found")
    if amount != payment.amount_paise or currency != payment.currency:
        record_audit_event(
            db,
            None,
            "payment.webhook_rejected",
            "subscription_payment",
            payment.id,
            details="Payment amount or currency did not match the stored order.",
        )
        db.commit()
        raise HTTPException(400, "Payment amount or currency does not match the order")
    if payment.gateway_payment_id not in {None, payment_id}:
        record_audit_event(
            db,
            None,
            "payment.webhook_rejected",
            "subscription_payment",
            payment.id,
            details="The order is already associated with a different payment.",
        )
        db.commit()
        raise HTTPException(409, "Payment order is already associated with another payment")

    event_record = PaymentWebhookEvent(
        gateway_event_id=event_id,
        gateway="razorpay",
        event_type=event_type,
        payload_sha256=payload_hash,
        processing_status="received",
    )
    db.add(event_record)
    if payment.status == "paid":
        event_record.processing_status = "processed"
        event_record.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "already_processed"}

    if event_type == "payment.failed":
        if payment.status not in {"created", "pending"}:
            event_record.processing_status = "ignored"
            event_record.processed_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "ignored"}
        description = entity.get("error_description")
        payment.failure_reason = (
            description[:300] if isinstance(description, str) else "Payment attempt failed."
        )
        event_record.processing_status = "processed"
        event_record.processed_at = datetime.now(timezone.utc)
        record_audit_event(
            db,
            None,
            "payment.failed",
            "subscription_payment",
            payment.id,
            details="The gateway reported a failed payment attempt; the order remains eligible for retry.",
        )
        db.commit()
        return {"status": "processed"}

    if payment.status not in {"created", "pending"}:
        event_record.processing_status = "ignored"
        event_record.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "ignored"}

    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.id == payment.subscription_id)
        .with_for_update()
        .first()
    )
    facility = db.get(Facility, payment.facility_id)
    if (
        subscription is None
        or facility is None
        or subscription.facility_id != payment.facility_id
    ):
        raise HTTPException(409, "Payment subscription is no longer available")

    now = datetime.now(timezone.utc)
    previous_period_end = subscription.current_period_end
    period_start = max(as_utc(previous_period_end), now) if previous_period_end else now
    period_end = add_billing_interval(period_start, payment.billing_interval_snapshot)
    payment.gateway_payment_id = payment_id
    payment.status = "paid"
    payment.paid_at = now
    payment.failure_reason = None
    subscription.plan_id = payment.plan_id
    subscription.billing_contact_user_id = facility.owner_user_id
    subscription.plan_name_snapshot = payment.plan_name_snapshot
    subscription.billing_interval_snapshot = payment.billing_interval_snapshot
    subscription.price_paise_snapshot = payment.amount_paise
    subscription.currency_snapshot = payment.currency
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.grace_period_end = period_end + timedelta(days=GRACE_PERIOD_DAYS)
    subscription.status = "active"
    subscription.cancel_at_period_end = False
    event_record.processing_status = "processed"
    event_record.processed_at = now
    record_audit_event(
        db,
        None,
        "subscription.renewed" if previous_period_end else "subscription.activated",
        "facility_subscription",
        subscription.id,
    )
    record_subscription_notice(
        db,
        subscription,
        f"payment:{payment.id}:paid",
        "renewal_success",
        "Your facility subscription payment was verified and access is active for the paid period.",
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        duplicate = (
            db.query(PaymentWebhookEvent.id)
            .filter(PaymentWebhookEvent.gateway_event_id == event_id)
            .first()
        )
        if duplicate:
            return {"status": "duplicate"}
        raise HTTPException(409, "Could not safely process the payment event") from error
    return {"status": "processed"}
