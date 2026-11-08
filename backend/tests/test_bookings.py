from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.auth import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, Booking, BookingDocument, Facility, Service, User


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

            appointment_at = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
            booking_request = {
                "facility_id": facility_id,
                "service_id": service_id,
                "appointment_at": appointment_at,
                "payment_method": "physical",
            }
            naive_request = {
                **booking_request,
                "appointment_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            }
            assert client.post(
                "/api/v1/bookings",
                json=naive_request,
                headers=patient_headers,
            ).status_code == 422
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
            assert booking["payment_status"] == "unpaid"
            assert booking["payment_due_paise"] == 10000
            assert "patient_email" not in booking
            with SessionLocal() as db:
                stored_booking = db.get(Booking, booking_id)
                assert stored_booking is not None
                assert stored_booking.patient_user_id == patient_id
                assert len(stored_booking.verification_code) == 64
                assert db.query(AuditEvent).filter(
                    AuditEvent.action == "booking.created",
                    AuditEvent.resource_id == booking_id,
                ).count() == 1
                patient = db.get(User, patient_id)
                assert patient is not None
                original_email = patient.email
                patient.email = f"renamed-{original_email}"
                db.commit()

            patient_bookings = client.get("/api/v1/bookings", headers=patient_headers)
            assert patient_bookings.status_code == 200
            assert patient_bookings.json()[0]["id"] == booking_id
            assert patient_bookings.json()[0]["provider_name"] == "Dr Example"
            assert client.get(
                f"/api/v1/bookings/{booking_id}",
                headers=patient_headers,
            ).status_code == 200
            with SessionLocal() as db:
                patient = db.get(User, patient_id)
                assert patient is not None
                patient.email = original_email
                db.commit()

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
            unpaid_check_in = client.post(
                "/api/v1/bookings/verify",
                json={"code": booking["verification_code"]},
                headers=staff_headers,
            )
            assert unpaid_check_in.status_code == 200
            assert unpaid_check_in.json()["valid"] is False
            assert "payment" in unpaid_check_in.json()["message"].lower()
            assert client.post(
                f"/api/v1/bookings/{booking_id}/payment",
                json={"reference": "patient-cannot-collect"},
                headers=patient_headers,
            ).status_code == 403
            assert client.post(
                f"/api/v1/bookings/{booking_id}/payment",
                json={"reference": "wrong-facility"},
                headers=other_staff_headers,
            ).status_code == 403
            payment = client.post(
                f"/api/v1/bookings/{booking_id}/payment",
                json={"reference": "receipt-123"},
                headers=staff_headers,
            )
            assert payment.status_code == 200
            assert payment.json()["payment_status"] == "paid"
            assert payment.json()["payment_amount_paise"] == 10000
            assert payment.json()["payment_reference"] == "receipt-123"
            with SessionLocal() as db:
                stored_booking = db.get(Booking, booking_id)
                assert stored_booking is not None
                assert stored_booking.payment_collected_by_user_id == staff_id
                assert stored_booking.payment_collected_at is not None
            admin_bookings = client.get("/api/v1/admin/bookings", headers=staff_headers)
            assert admin_bookings.status_code == 200
            paid_booking = next(row for row in admin_bookings.json() if row["id"] == booking_id)
            assert paid_booking["payment_collector_name"] == "Test facility_staff"
            assert paid_booking["payment_reference"] == "receipt-123"
            assert paid_booking["payment_amount_paise"] == 10000
            assert paid_booking["provider_name"] == "Dr Example"
            assert client.post(
                f"/api/v1/bookings/{booking_id}/payment",
                json={"reference": "duplicate"},
                headers=staff_headers,
            ).status_code == 409

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
                json={
                    **booking_request,
                    "appointment_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                },
                headers=patient_headers,
            )
            assert second_booking.status_code == 201
            second_booking_id = second_booking.json()["id"]
            with SessionLocal() as db:
                stored_booking = db.get(Booking, second_booking_id)
                assert stored_booking is not None
                stored_booking.appointment_at = datetime.now(timezone.utc) + timedelta(minutes=31)
                db.commit()
            early_check_in = client.post(
                "/api/v1/bookings/verify",
                json={"code": second_booking.json()["verification_code"]},
                headers=staff_headers,
            )
            assert early_check_in.json()["valid"] is False
            assert "opens 30 minutes" in early_check_in.json()["message"]
            with SessionLocal() as db:
                stored_booking = db.get(Booking, second_booking_id)
                assert stored_booking is not None
                stored_booking.appointment_at = datetime.now(timezone.utc) - timedelta(minutes=61)
                db.commit()
            late_check_in = client.post(
                "/api/v1/bookings/verify",
                json={"code": second_booking.json()["verification_code"]},
                headers=staff_headers,
            )
            assert late_check_in.json()["valid"] is False
            assert "window has closed" in late_check_in.json()["message"]
            with SessionLocal() as db:
                stored_booking = db.get(Booking, second_booking_id)
                assert stored_booking is not None
                stored_booking.appointment_at = datetime.now(timezone.utc) + timedelta(days=2)
                db.commit()
            cancelled = client.post(
                f"/api/v1/bookings/{second_booking_id}/cancel",
                headers=patient_headers,
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert client.post(
                f"/api/v1/bookings/{second_booking_id}/cancel",
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

def test_booking_documents_are_private_validated_and_downloadable(platform_admin_headers):
    suffix = uuid4().hex
    facility_id = booking_id = None
    user_ids: list[int] = []

    with TestClient(app) as client:
        try:
            facility_response = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"Document Center {suffix}",
                    "facility_type": "hospital",
                    "address": "2 Document Way",
                    "city": "Document City",
                    "phone": "555-0120",
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
                    "provider_name": "Dr Document",
                    "fee_paise": 0,
                },
                headers=platform_admin_headers,
            )
            assert service_response.status_code == 201

            with SessionLocal() as db:
                patient, patient_headers = add_user(db, "patient")
                staff, staff_headers = add_user(db, "facility_staff", facility_id=facility_id)
                other_staff, other_staff_headers = add_user(db, "facility_staff")
                other_patient, other_patient_headers = add_user(db, "patient")
                user_ids = [patient.id, staff.id, other_staff.id, other_patient.id]

            created = client.post(
                "/api/v1/bookings",
                json={
                    "facility_id": facility_id,
                    "service_id": service_response.json()["id"],
                    "appointment_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    "payment_method": "physical",
                },
                headers=patient_headers,
            )
            assert created.status_code == 201
            booking_id = created.json()["id"]

            assert client.get(
                f"/api/v1/bookings/{booking_id}/documents",
                headers=other_patient_headers,
            ).status_code == 404
            assert client.get(
                f"/api/v1/bookings/{booking_id}/documents",
                headers=other_staff_headers,
            ).status_code == 404
            assert client.post(
                f"/api/v1/bookings/{booking_id}/documents",
                files=[("files", ("not-owner.pdf", b"%PDF-test", "application/pdf"))],
                headers=other_staff_headers,
            ).status_code == 404
            assert client.get(
                f"/api/v1/bookings/{booking_id}/documents",
                headers=platform_admin_headers,
            ).status_code == 404

            pdf_content = b"%PDF-1.7\nfake test report"
            jpeg_content = b"\xff\xd8\xfffake jpeg test"
            png_content = b"\x89PNG\r\n\x1a\nfake png test"
            uploaded = client.post(
                f"/api/v1/bookings/{booking_id}/documents",
                files=[
                    ("files", ("visit-report.pdf", pdf_content, "application/pdf")),
                    ("files", ("previous-visit.jpg", jpeg_content, "image/jpeg")),
                    ("files", ("prescription.png", png_content, "image/png")),
                ],
                headers=patient_headers,
            )
            assert uploaded.status_code == 201
            document = next(
                item for item in uploaded.json() if item["filename"] == "visit-report.pdf"
            )
            assert document["filename"] == "visit-report.pdf"
            assert document["size_bytes"] == len(pdf_content)
            assert "content" not in document
            assert "uploaded_by_user_id" not in document
            assert {item["media_type"] for item in uploaded.json()} == {
                "application/pdf",
                "image/jpeg",
                "image/png",
            }

            patient_list = client.get(
                f"/api/v1/bookings/{booking_id}/documents",
                headers=patient_headers,
            )
            assert patient_list.status_code == 200
            staff_list = client.get(
                f"/api/v1/bookings/{booking_id}/documents",
                headers=staff_headers,
            )
            assert staff_list.status_code == 200
            assert staff_list.json()[0]["id"] == document["id"]

            download = client.get(
                f"/api/v1/bookings/{booking_id}/documents/{document['id']}",
                headers=staff_headers,
            )
            assert download.status_code == 200
            assert download.content == pdf_content
            assert download.headers["content-type"] == "application/pdf"
            assert download.headers["x-content-type-options"] == "nosniff"
            assert download.headers["cache-control"] == "private, no-store"
            patient_download = client.get(
                f"/api/v1/bookings/{booking_id}/documents/{document['id']}",
                headers=patient_headers,
            )
            assert patient_download.status_code == 200
            assert patient_download.content == pdf_content
            assert client.get(
                f"/api/v1/bookings/{booking_id}/documents/{document['id']}",
                headers=other_staff_headers,
            ).status_code == 404

            bad_signature = client.post(
                f"/api/v1/bookings/{booking_id}/documents",
                files=[("files", ("fake.pdf", b"not a pdf", "application/pdf"))],
                headers=patient_headers,
            )
            assert bad_signature.status_code == 422
            unsupported = client.post(
                f"/api/v1/bookings/{booking_id}/documents",
                files=[("files", ("script.txt", b"hello", "text/plain"))],
                headers=patient_headers,
            )
            assert unsupported.status_code == 415
            too_large = client.post(
                f"/api/v1/bookings/{booking_id}/documents",
                files=[
                    (
                        "files",
                        ("large.pdf", b"%PDF-" + b"x" * (10 * 1024 * 1024), "application/pdf"),
                    )
                ],
                headers=patient_headers,
            )
            assert too_large.status_code == 413
            too_many = client.post(
                f"/api/v1/bookings/{booking_id}/documents",
                files=[
                    ("files", (f"extra-{index}.pdf", b"%PDF-test", "application/pdf"))
                    for index in range(3)
                ],
                headers=patient_headers,
            )
            assert too_many.status_code == 413

            with SessionLocal() as db:
                assert db.query(BookingDocument).filter(
                    BookingDocument.booking_id == booking_id
                ).count() == 3
                assert db.query(AuditEvent).filter(
                    AuditEvent.action == "booking.document_downloaded",
                    AuditEvent.resource_id == document["id"],
                ).count() == 2
        finally:
            with SessionLocal() as db:
                if booking_id:
                    db.query(Booking).filter(Booking.id == booking_id).delete()
                for user_id in user_ids:
                    db.query(AuditEvent).filter(AuditEvent.actor_user_id == user_id).delete()
                    user = db.get(User, user_id)
                    if user:
                        db.delete(user)
                if facility_id:
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    facility = db.get(Facility, facility_id)
                    if facility:
                        db.delete(facility)
                db.commit()
