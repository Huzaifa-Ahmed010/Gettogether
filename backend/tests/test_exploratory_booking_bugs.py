from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, Booking, Facility, Service, User

from test_bookings import add_user


def test_doctor_slot_is_shared_across_service_categories_and_released_on_cancel(
    platform_admin_headers,
):
    suffix = uuid4().hex
    facility_id = None
    user_ids = []
    booking_ids = []

    with TestClient(app) as client:
        try:
            with SessionLocal() as db:
                facility = Facility(
                    name=f"Slot Center {suffix}",
                    facility_type="hospital",
                    address="1 Slot Test Road",
                    city="Test City",
                    phone="",
                    description="",
                    timezone="Asia/Kolkata",
                    is_active=True,
                )
                db.add(facility)
                db.flush()
                facility_id = facility.id

                staff, staff_headers = add_user(db, "facility_staff", facility_id=facility_id)
                patient_one, patient_one_headers = add_user(db, "patient")
                patient_two, patient_two_headers = add_user(db, "patient")
                user_ids.extend([staff.id, patient_one.id, patient_two.id])

                service_one = Service(
                    facility_id=facility_id,
                    name="Cardiology consultation",
                    category="Cardiology",
                    service_type="doctor",
                    provider_name="Dr Shared",
                    provider_key="doctor-shared-slot-test",
                    fee_paise=10000,
                    is_active=True,
                )
                service_two = Service(
                    facility_id=facility_id,
                    name="General consultation",
                    category="General Medicine",
                    service_type="doctor",
                    provider_name="Dr Shared",
                    provider_key="doctor-shared-slot-test",
                    fee_paise=10000,
                    is_active=True,
                )
                db.add_all([service_one, service_two])
                db.commit()
                service_one_id = service_one.id
                service_two_id = service_two.id

            appointment_at = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
            payload = {
                "facility_id": facility_id,
                "appointment_at": appointment_at,
                "payment_method": "physical",
            }

            # Management roles cannot create bookings, even by calling the API directly.
            assert client.post(
                "/api/v1/bookings",
                json={**payload, "service_id": service_one_id},
                headers=platform_admin_headers,
            ).status_code == 403
            assert client.post(
                "/api/v1/bookings",
                json={**payload, "service_id": service_one_id},
                headers=staff_headers,
            ).status_code == 403

            first = client.post(
                "/api/v1/bookings",
                json={**payload, "service_id": service_one_id},
                headers=patient_one_headers,
            )
            assert first.status_code == 201
            first_booking_id = first.json()["id"]
            booking_ids.append(first_booking_id)

            # Same doctor, different service/category record: slot is still held.
            conflict = client.post(
                "/api/v1/bookings",
                json={**payload, "service_id": service_two_id},
                headers=patient_two_headers,
            )
            assert conflict.status_code == 409

            cancelled = client.post(
                f"/api/v1/bookings/{first_booking_id}/cancel",
                headers=patient_one_headers,
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"

            # Cancellation releases the slot for another category/service record.
            retry = client.post(
                "/api/v1/bookings",
                json={**payload, "service_id": service_two_id},
                headers=patient_two_headers,
            )
            assert retry.status_code == 201
            booking_ids.append(retry.json()["id"])
        finally:
            with SessionLocal() as db:
                if booking_ids:
                    db.query(Booking).filter(Booking.id.in_(booking_ids)).delete(
                        synchronize_session=False
                    )
                for user_id in user_ids:
                    db.query(AuditEvent).filter(AuditEvent.actor_user_id == user_id).delete(
                        synchronize_session=False
                    )
                    user = db.get(User, user_id)
                    if user is not None:
                        db.delete(user)
                if facility_id is not None:
                    db.query(Service).filter(Service.facility_id == facility_id).delete(
                        synchronize_session=False
                    )
                    facility = db.get(Facility, facility_id)
                    if facility is not None:
                        db.delete(facility)
                db.commit()
