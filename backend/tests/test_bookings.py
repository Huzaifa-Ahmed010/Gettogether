from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.auth import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, Booking, Facility, Service, User


def add_user(db, role, *, facility_id=None):
    user = User(
        name=f"Test {role}",
        email=f"{role}-{uuid4().hex}@example.com",
        password_hash="test-only-password-hash",
        role=role,
        email_verified=True,
        facility_id=facility_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token(user)}"}


def test_booking_permissions_creation_and_staff_verification(platform_admin_headers):
    suffix = uuid4().hex
    facility_id = None
    patient_id = staff_id = other_staff_id = None

    with TestClient(app) as client:
        try:
            facility_response = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"Booking Center {suffix}",
                    "facility_type": "hospital",
                    "address": "1 Appointment Way",
                    "city": "Booking City",
                    "phone": "555-0110",
                },
                headers=platform_admin_headers,
            )
            assert facility_response.status_code == 201
            facility_id = facility_response.json()["id"]
            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Consultation {suffix}",
                    "category": "Primary care",
                    "service_type": "doctor",
                    "provider_name": "Dr Example",
                    "fee_paise": 10000,
                },
                headers=platform_admin_headers,
            )
            assert service_response.status_code == 201
            service_id = service_response.json()["id"]

            with SessionLocal() as db:
                patient, patient_headers = add_user(db, "patient")
                patient_id = patient.id
                staff, staff_headers = add_user(db, "facility_staff", facility_id=facility_id)
                staff_id = staff.id
                other_staff, other_staff_headers = add_user(db, "facility_staff")
                other_staff_id = other_staff.id

            appointment_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
            booking_request = {
                "facility_id": facility_id,
                "service_id": service_id,
                "appointment_at": appointment_at,
                "payment_method": "physical",
            }
            assert client.post("/api/v1/bookings", json=booking_request).status_code == 401
            assert client.post(
                "/api/v1/bookings",
                json={**booking_request, "payment_method": "online"},
                headers=patient_headers,
            ).status_code == 422

            created = client.post(
                "/api/v1/bookings",
                json=booking_request,
                headers=patient_headers,
            )
            assert created.status_code == 201
            booking = created.json()
            booking_id = booking["id"]
            assert len(booking["verification_code"]) == 6
            assert "patient_email" not in booking
            with SessionLocal() as db:
                stored_booking = db.get(Booking, booking_id)
                assert stored_booking is not None
                assert len(stored_booking.verification_code) == 64
                assert db.query(AuditEvent).filter(
                    AuditEvent.action == "booking.created",
                    AuditEvent.resource_id == booking_id,
                ).count() == 1

            assert client.get(
                f"/api/v1/bookings/{booking_id}",
                headers=other_staff_headers,
            ).status_code == 403
            assert client.post(
                "/api/v1/bookings/verify",
                json={"code": booking["verification_code"]},
                headers=patient_headers,
            ).status_code == 403
            assert client.post(
                "/api/v1/bookings/verify",
                json={"code": booking["verification_code"]},
                headers=other_staff_headers,
            ).status_code == 403

            verified = client.post(
                "/api/v1/bookings/verify",
                json={"code": booking["verification_code"]},
                headers=staff_headers,
            )
            assert verified.status_code == 200
            assert verified.json()["valid"] is True
            assert client.post(
                "/api/v1/bookings/verify",
                json={"code": booking["verification_code"]},
                headers=staff_headers,
            ).json()["valid"] is False
            assert client.get(
                "/api/v1/bookings",
                headers=patient_headers,
            ).json()[0]["status"] == "verified"

            second_booking = client.post(
                "/api/v1/bookings",
                json=booking_request,
                headers=patient_headers,
            )
            assert second_booking.status_code == 201
            cancelled = client.post(
                f"/api/v1/bookings/{second_booking.json()['id']}/cancel",
                headers=patient_headers,
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert client.post(
                f"/api/v1/bookings/{second_booking.json()['id']}/cancel",
                headers=patient_headers,
            ).status_code == 409
        finally:
            with SessionLocal() as db:
                if patient_id:
                    patient = db.get(User, patient_id)
                    if patient:
                        db.query(Booking).filter(Booking.patient_email == patient.email).delete()
                for user_id in (staff_id, other_staff_id, patient_id):
                    if user_id:
                        db.query(AuditEvent).filter(AuditEvent.actor_user_id == user_id).delete()
                for user_id in (staff_id, other_staff_id, patient_id):
                    if user_id:
                        user = db.get(User, user_id)
                        if user:
                            db.delete(user)
                if facility_id:
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    facility = db.get(Facility, facility_id)
                    if facility:
                        db.delete(facility)
                db.commit()
