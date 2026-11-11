import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AuditEvent,
    Booking,
    Facility,
    FacilitySubscription,
    PaymentWebhookEvent,
    Service,
    SubscriptionPayment,
    SubscriptionPlan,
    User,
)
from app.services.subscriptions import add_billing_interval, effective_subscription_status


def test_subscription_plans_checkout_and_signed_webhook(
    platform_admin_headers,
    account_factory,
    monkeypatch,
):
    suffix = uuid4().hex
    facility_id = staff_id = other_staff_id = None
    monkeypatch.setattr(settings, "razorpay_key_id", "test-key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "test-secret")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "test-webhook-secret")

    import app.api.routes.subscriptions as subscription_routes

    monkeypatch.setattr(subscription_routes, "create_order", lambda **_: f"order-{suffix}")

    with TestClient(app) as client:
        try:
            staff_id, staff_headers = account_factory("facility_staff")
            facility_response = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"Billing Center {suffix}",
                    "facility_type": "hospital",
                    "address": "5 Billing Road",
                    "city": "Billtown",
                    "phone": "",
                },
                headers=staff_headers,
            )
            assert facility_response.status_code == 201
            facility_id = facility_response.json()["id"]
            with SessionLocal() as db:
                db.query(FacilitySubscription).filter(
                    FacilitySubscription.facility_id == facility_id
                ).delete()
                db.commit()
            owner_response = client.post(
                f"/api/v1/admin/facilities/{facility_id}/owner",
                json={"user_id": staff_id},
                headers=platform_admin_headers,
            )
            assert owner_response.status_code == 200
            other_staff_id, _ = account_factory("facility_staff", facility_id=facility_id)
            assert [
                account["id"]
                for account in client.get(
                    f"/api/v1/admin/facilities/{facility_id}/staff",
                    headers=platform_admin_headers,
                ).json()
            ] == [staff_id, other_staff_id]

            plan_response = client.post(
                "/api/v1/admin/subscription-plans",
                json={
                    "name": f"Monthly {suffix}",
                    "description": "Monthly facility access",
                    "billing_interval": "monthly",
                    "price_paise": None,
                    "is_active": False,
                },
                headers=platform_admin_headers,
            )
            assert plan_response.status_code == 201
            plan_id = plan_response.json()["id"]
            assert client.patch(
                f"/api/v1/admin/subscription-plans/{plan_id}",
                json={"is_active": True},
                headers=platform_admin_headers,
            ).status_code == 422
            activated_plan = client.patch(
                f"/api/v1/admin/subscription-plans/{plan_id}",
                json={"price_paise": 250000, "is_active": True},
                headers=platform_admin_headers,
            )
            assert activated_plan.status_code == 200
            assert activated_plan.json()["price_paise"] == 250000

            plans_response = client.get(
                "/api/v1/facility/subscription/plans",
                headers=staff_headers,
            )
            assert plans_response.status_code == 200
            assert [plan["id"] for plan in plans_response.json()] == [plan_id]
            assert client.get(
                "/api/v1/facility/subscription",
                headers=staff_headers,
            ).json()["status"] == "unsubscribed"

            checkout = client.post(
                "/api/v1/facility/subscription/checkout",
                json={"plan_id": plan_id},
                headers=staff_headers,
            )
            assert checkout.status_code == 201
            checkout_data = checkout.json()
            with SessionLocal() as db:
                payment = db.get(SubscriptionPayment, checkout_data["payment_id"])
                assert payment is not None
                assert payment.status == "pending"
                assert payment.gateway_order_id == checkout_data["order_id"]
                subscription = db.get(FacilitySubscription, payment.subscription_id)
                assert subscription is not None
                assert effective_subscription_status(subscription) == "pending_payment"

            body = json.dumps(
                {
                    "event": "payment.captured",
                    "payload": {
                        "payment": {
                            "entity": {
                                "id": f"pay-{suffix}",
                                "order_id": checkout_data["order_id"],
                                "amount": 250000,
                                "currency": "INR",
                            }
                        }
                    },
                }
            ).encode()
            signature = hmac.new(
                b"test-webhook-secret",
                body,
                hashlib.sha256,
            ).hexdigest()
            headers = {
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": f"event-{suffix}",
            }
            processed = client.post(
                "/api/v1/webhooks/razorpay",
                content=body,
                headers=headers,
            )
            assert processed.status_code == 200
            assert processed.json()["status"] == "processed"
            duplicate = client.post(
                "/api/v1/webhooks/razorpay",
                content=body,
                headers=headers,
            )
            assert duplicate.status_code == 200
            assert duplicate.json()["status"] == "duplicate"
            with SessionLocal() as db:
                payment = db.get(SubscriptionPayment, checkout_data["payment_id"])
                assert payment is not None
                assert payment.status == "paid"
                subscription_id = payment.subscription_id
                subscription = db.get(FacilitySubscription, payment.subscription_id)
                assert subscription is not None
                assert effective_subscription_status(subscription) == "active"
                assert subscription.current_period_end > subscription.current_period_start
                assert db.query(PaymentWebhookEvent).filter(
                    PaymentWebhookEvent.gateway_event_id == f"event-{suffix}"
                ).count() == 1
                assert db.query(AuditEvent).filter(
                    AuditEvent.action == "subscription.activated",
                    AuditEvent.resource_id == subscription.id,
                ).count() == 1
            assert client.get(
                "/api/v1/admin/subscriptions",
                headers=platform_admin_headers,
            ).json()[0]["status"] == "active"
            assert client.get(
                "/api/v1/admin/subscription-payments",
                headers=platform_admin_headers,
            ).json()[0]["status"] == "paid"
            extended = client.post(
                f"/api/v1/admin/subscriptions/{subscription_id}/extend",
                json={"days": 14, "reason": "Approved service recovery credit."},
                headers=platform_admin_headers,
            )
            assert extended.status_code == 200
            assert extended.json()["status"] == "active"
            transferred = client.post(
                f"/api/v1/admin/facilities/{facility_id}/owner",
                json={"user_id": other_staff_id},
                headers=platform_admin_headers,
            )
            assert transferred.status_code == 200
            assert transferred.json()["owner_user_id"] == other_staff_id
            with SessionLocal() as db:
                subscription = db.get(FacilitySubscription, subscription_id)
                assert subscription is not None
                assert subscription.billing_contact_user_id == other_staff_id
                assert db.query(AuditEvent).filter(
                    AuditEvent.action == "subscription.admin_extended",
                    AuditEvent.resource_id == subscription_id,
                    AuditEvent.details.contains("Approved service recovery credit."),
                ).count() == 1

            invalid = client.post(
                "/api/v1/webhooks/razorpay",
                content=body,
                headers={
                    "X-Razorpay-Signature": "invalid",
                    "X-Razorpay-Event-Id": f"bad-{suffix}",
                },
            )
            assert invalid.status_code == 400
        finally:
            with SessionLocal() as db:
                if facility_id:
                    facility = db.get(Facility, facility_id)
                    if facility:
                        db.delete(facility)
                for account_id in (staff_id, other_staff_id):
                    if account_id:
                        staff = db.get(User, account_id)
                        if staff:
                            db.delete(staff)
                db.query(SubscriptionPlan).filter(
                    SubscriptionPlan.name == f"Monthly {suffix}"
                ).delete()
                db.commit()


def test_billing_calendar_and_grace_period_states():
    assert add_billing_interval(
        datetime(2024, 1, 31, 12, tzinfo=timezone.utc),
        "monthly",
    ) == datetime(2024, 2, 29, 12, tzinfo=timezone.utc)
    assert add_billing_interval(
        datetime(2024, 11, 30, 12, tzinfo=timezone.utc),
        "quarterly",
    ) == datetime(2025, 2, 28, 12, tzinfo=timezone.utc)
    assert add_billing_interval(
        datetime(2024, 2, 29, 12, tzinfo=timezone.utc),
        "yearly",
    ) == datetime(2025, 2, 28, 12, tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    subscription = FacilitySubscription(
        status="active",
        current_period_end=now - timedelta(days=2),
        grace_period_end=now + timedelta(days=5),
    )
    assert effective_subscription_status(subscription, now) == "grace_period"
    subscription.grace_period_end = now - timedelta(seconds=1)
    assert effective_subscription_status(subscription, now) == "expired"


def test_staff_facility_onboarding_and_booking_rejection(
    platform_admin_headers,
    account_factory,
    grant_facility_entitlement,
):
    suffix = uuid4().hex
    staff_id, staff_headers = account_factory("facility_staff")
    patient_id, patient_headers = account_factory("patient")
    facility_id = None
    service_id = None
    booking_id = None

    with TestClient(app) as client:
        try:
            onboarding = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"New Facility {suffix}",
                    "facility_type": "diagnostic",
                    "address": "7 New Facility Street",
                    "city": "Newtown",
                    "phone": "",
                },
                headers=staff_headers,
            )
            assert onboarding.status_code == 201
            facility = onboarding.json()
            facility_id = facility["id"]
            assert facility["is_active"] is False
            with SessionLocal() as db:
                staff = db.get(User, staff_id)
                assert staff is not None
                assert staff.facility_id == facility_id
                assert db.get(Facility, facility_id).owner_user_id == staff_id
            assert client.get(
                f"/api/v1/facilities/{facility_id}",
            ).status_code == 404

            approved = client.patch(
                f"/api/v1/admin/facilities/{facility_id}",
                json={"is_active": True},
                headers=platform_admin_headers,
            )
            assert approved.status_code == 200
            grant_facility_entitlement(facility_id)
            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Consultation {suffix}",
                    "category": "Imaging",
                    "service_type": "diagnostic",
                    "provider_name": "",
                    "fee_paise": 0,
                },
                headers=staff_headers,
            )
            assert service_response.status_code == 201
            service_id = service_response.json()["id"]
            request = client.post(
                "/api/v1/bookings",
                json={
                    "facility_id": facility_id,
                    "service_id": service_id,
                    "appointment_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                    "payment_method": "physical",
                },
                headers=patient_headers,
            )
            assert request.status_code == 201
            booking_id = request.json()["id"]
            rejected = client.post(
                f"/api/v1/admin/bookings/{booking_id}/reject",
                json={"reason": "The requested time is unavailable."},
                headers=staff_headers,
            )
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "rejected"
            assert rejected.json()["rejection_reason"] == "The requested time is unavailable."
            assert "verification_code" not in rejected.json()
        finally:
            with SessionLocal() as db:
                if booking_id:
                    db.query(Booking).filter(Booking.id == booking_id).delete()
                if service_id:
                    db.query(Service).filter(Service.id == service_id).delete()
                if facility_id:
                    db.query(FacilitySubscription).filter(
                        FacilitySubscription.facility_id == facility_id
                    ).delete()
                    facility = db.get(Facility, facility_id)
                    if facility:
                        db.delete(facility)
                for user_id in (staff_id, patient_id):
                    user = db.get(User, user_id)
                    if user:
                        db.delete(user)
                db.commit()
