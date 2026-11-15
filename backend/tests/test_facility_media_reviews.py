from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, Booking, Facility, FacilityReview, Service, User


def test_facility_media_and_completed_appointment_reviews(
    account_factory,
    platform_admin_headers,
):
    suffix = uuid4().hex
    staff_id, staff_headers = account_factory("facility_staff")
    patient_id, patient_headers = account_factory("patient")
    other_patient_id, other_patient_headers = account_factory("patient")
    other_staff_id, other_staff_headers = account_factory("facility_staff")
    facility_id = None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"Media Center {suffix}",
                    "facility_type": "hospital",
                    "address": "5 Media Way",
                    "city": "Media City",
                    "phone": "555-0150",
                    "description": "A test facility.",
                },
                headers=staff_headers,
            )
            assert response.status_code == 201
            facility_id = response.json()["id"]
            assert client.patch(
                f"/api/v1/admin/facilities/{facility_id}",
                json={"is_active": True},
                headers=platform_admin_headers,
            ).status_code == 200

            png = b"\x89PNG\r\n\x1a\n" + b"test image"
            uploaded_image = client.put(
                f"/api/v1/facilities/{facility_id}/image",
                files={"file": ("facility.png", png, "image/png")},
                headers=staff_headers,
            )
            assert uploaded_image.status_code == 200
            public_image = client.get(f"/api/v1/facilities/{facility_id}/image")
            assert public_image.status_code == 200
            assert public_image.content == png
            assert public_image.headers["content-type"] == "image/png"
            assert public_image.headers["x-content-type-options"] == "nosniff"
            assert client.put(
                f"/api/v1/facilities/{facility_id}/image",
                files={"file": ("facility.svg", b"<svg/>", "image/svg+xml")},
                headers=staff_headers,
            ).status_code == 415
            assert client.put(
                f"/api/v1/facilities/{facility_id}/image",
                files={"file": ("facility.png", png, "image/png")},
                headers=other_staff_headers,
            ).status_code == 403

            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Consultation {suffix}",
                    "category": "Primary care",
                    "service_type": "doctor",
                    "provider_name": "Dr Media",
                    "fee_paise": 0,
                },
                headers=staff_headers,
            )
            assert service_response.status_code == 201
            service_id = service_response.json()["id"]
            service_image = client.put(
                f"/api/v1/facilities/{facility_id}/services/{service_id}/image",
                files={"file": ("doctor.webp", b"RIFF1234WEBPtest", "image/webp")},
                headers=staff_headers,
            )
            assert service_image.status_code == 200
            assert client.get(
                f"/api/v1/facilities/{facility_id}/services/{service_id}/image"
            ).headers["content-type"] == "image/webp"

            booking_response = client.post(
                "/api/v1/bookings",
                json={
                    "facility_id": facility_id,
                    "service_id": service_id,
                    "appointment_at": (
                        datetime.now(timezone.utc) + timedelta(days=1)
                    ).isoformat(),
                    "payment_method": "physical",
                },
                headers=patient_headers,
            )
            assert booking_response.status_code == 201
            booking_id = booking_response.json()["id"]
            review_url = f"/api/v1/bookings/{booking_id}/review"
            review_payload = {"rating": 5, "comment": "Helpful and welcoming."}
            assert client.post(
                review_url,
                json=review_payload,
                headers=patient_headers,
            ).status_code == 409
            assert client.post(
                review_url,
                json=review_payload,
                headers=other_patient_headers,
            ).status_code == 404

            with SessionLocal() as db:
                booking = db.get(Booking, booking_id)
                assert booking is not None
                booking.status = "completed"
                db.commit()

            created_review = client.post(
                review_url,
                json=review_payload,
                headers=patient_headers,
            )
            assert created_review.status_code == 201
            assert created_review.json()["booking_id"] == booking_id
            assert client.post(
                review_url,
                json=review_payload,
                headers=patient_headers,
            ).status_code == 409

            public_reviews = client.get(
                f"/api/v1/facilities/{facility_id}/reviews"
            )
            assert public_reviews.status_code == 200
            public_body = public_reviews.json()
            assert public_body["ratings_count"] == 1
            assert public_body["average_rating"] == 5
            assert "booking_id" not in public_body["reviews"][0]
            assert "patient_user_id" not in public_body["reviews"][0]

            own_reviews = client.get(
                "/api/v1/bookings/reviews/mine",
                headers=patient_headers,
            )
            assert own_reviews.status_code == 200
            assert own_reviews.json()[0]["booking_id"] == booking_id
    finally:
        if facility_id is not None:
            with SessionLocal() as db:
                db.query(FacilityReview).filter(
                    FacilityReview.facility_id == facility_id
                ).delete(synchronize_session=False)
                db.query(Booking).filter(
                    Booking.facility_id == facility_id
                ).delete(synchronize_session=False)
                db.query(Service).filter(
                    Service.facility_id == facility_id
                ).delete(synchronize_session=False)
                user_ids = [staff_id, patient_id, other_patient_id, other_staff_id]
                db.query(User).filter(User.id.in_(user_ids)).update(
                    {User.facility_id: None},
                    synchronize_session=False,
                )
                facility = db.get(Facility, facility_id)
                if facility is not None:
                    facility.owner_user_id = None
                    db.delete(facility)
                db.query(AuditEvent).filter(
                    AuditEvent.actor_user_id.in_(user_ids)
                ).delete(synchronize_session=False)
                db.commit()
