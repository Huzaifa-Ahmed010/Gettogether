from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.auth import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, Booking, Facility, Service, User


def create_account(role: str, *, facility_id: int | None = None, verified: bool = True):
    with SessionLocal() as db:
        account = User(
            name=f"Test {role}",
            email=f"{role}-{uuid4().hex}@example.com",
            password_hash="test-only-password-hash",
            role=role,
            email_verified=verified,
            facility_id=facility_id,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        headers = {"Authorization": f"Bearer {create_access_token(account)}"}
        return account.id, account.email, headers


def cleanup_accounts(*account_ids: int):
    with SessionLocal() as db:
        for account_id in account_ids:
            account = db.get(User, account_id)
            if account is not None:
                db.query(AuditEvent).filter(AuditEvent.actor_user_id == account.id).delete()
                db.delete(account)
        db.commit()


def test_directory_management_is_role_and_facility_scoped(platform_admin_headers):
    suffix = uuid4().hex
    facility_ids: list[int] = []
    account_ids: list[int] = []
    service_ids: list[int] = []
    with TestClient(app) as client:
        try:
            assert client.get("/api/v1/admin/facilities").status_code == 401
            facility_payload = {
                "name": f"Admin Center {suffix}",
                "facility_type": "hospital",
                "address": "1 Admin Road",
                "city": "Admin City",
                "phone": "555-0123",
            }
            first = client.post(
                "/api/v1/facilities",
                json=facility_payload,
                headers=platform_admin_headers,
            )
            second = client.post(
                "/api/v1/facilities",
                json={**facility_payload, "name": f"Other Center {suffix}"},
                headers=platform_admin_headers,
            )
            assert first.status_code == second.status_code == 201
            facility_id = first.json()["id"]
            other_facility_id = second.json()["id"]
            facility_ids.extend((facility_id, other_facility_id))

            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Family medicine {suffix}",
                    "category": "Primary care",
                    "service_type": "doctor",
                    "provider_name": "Dr Demo",
                    "fee_paise": 25000,
                },
                headers=platform_admin_headers,
            )
            assert service_response.status_code == 201
            service_id = service_response.json()["id"]
            service_ids.append(service_id)

            staff_id, _, staff_headers = create_account(
                "facility_staff",
                facility_id=facility_id,
            )
            other_staff_id, _, other_staff_headers = create_account(
                "facility_staff",
                facility_id=other_facility_id,
            )
            account_ids.extend((staff_id, other_staff_id))
            patient_id, _, patient_headers = create_account("patient")
            account_ids.append(patient_id)

            managed = client.get("/api/v1/admin/facilities", headers=staff_headers)
            assert managed.status_code == 200
            assert [facility["id"] for facility in managed.json()] == [facility_id]
            assert client.get(
                "/api/v1/admin/facilities",
                headers=patient_headers,
            ).status_code == 403

            updated_service = client.patch(
                f"/api/v1/admin/facilities/{facility_id}/services/{service_id}",
                json={"fee_paise": 30000},
                headers=staff_headers,
            )
            assert updated_service.status_code == 200
            assert updated_service.json()["fee_paise"] == 30000
            assert client.patch(
                f"/api/v1/admin/facilities/{other_facility_id}",
                json={"city": "Different City"},
                headers=staff_headers,
            ).status_code == 403
            assert client.patch(
                f"/api/v1/admin/facilities/{facility_id}",
                json={"is_active": False},
                headers=staff_headers,
            ).status_code == 403

            deactivated = client.patch(
                f"/api/v1/admin/facilities/{facility_id}/services/{service_id}",
                json={"is_active": False},
                headers=platform_admin_headers,
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["is_active"] is False
            assert client.get("/api/v1/admin/dashboard", headers=staff_headers).json() == {
                "facilities": 1,
                "services": 0,
                "bookings": 0,
                "users": None,
            }
        finally:
            with SessionLocal() as db:
                for facility_id in facility_ids:
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    db.query(Booking).filter(Booking.facility_id == facility_id).delete()
                    db.query(User).filter(User.facility_id == facility_id).update(
                        {User.facility_id: None},
                        synchronize_session=False,
                    )
                    db.query(AuditEvent).filter(
                        AuditEvent.resource_type == "facility",
                        AuditEvent.resource_id == facility_id,
                    ).delete()
                    facility = db.get(Facility, facility_id)
                    if facility is not None:
                        db.delete(facility)
                for service_id in service_ids:
                    db.query(AuditEvent).filter(
                        AuditEvent.resource_type == "service",
                        AuditEvent.resource_id == service_id,
                    ).delete()
                db.commit()
            cleanup_accounts(*account_ids)


def test_booking_and_user_admin_permissions(platform_admin_headers):
    suffix = uuid4().hex
    facility_id = None
    account_ids: list[int] = []
    with TestClient(app) as client:
        try:
            facility_response = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"Booking Admin Center {suffix}",
                    "facility_type": "hospital",
                    "address": "2 Booking Road",
                    "city": "Booking City",
                    "phone": "555-0124",
                },
                headers=platform_admin_headers,
            )
            assert facility_response.status_code == 201
            facility_id = facility_response.json()["id"]
            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Checkup {suffix}",
                    "category": "Primary care",
                    "service_type": "doctor",
                    "provider_name": "Dr Example",
                    "fee_paise": 10000,
                },
                headers=platform_admin_headers,
            )
            assert service_response.status_code == 201
            service_id = service_response.json()["id"]

            patient_id, patient_email, patient_headers = create_account("patient")
            staff_id, _, staff_headers = create_account(
                "facility_staff",
                facility_id=facility_id,
            )
            other_staff_id, _, other_staff_headers = create_account(
                "facility_staff",
            )
            account_ids.extend((patient_id, staff_id, other_staff_id))

            booking_response = client.post(
                "/api/v1/bookings",
                json={
                    "facility_id": facility_id,
                    "service_id": service_id,
                    "appointment_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                    "payment_method": "physical",
                },
                headers=patient_headers,
            )
            assert booking_response.status_code == 201
            booking_id = booking_response.json()["id"]

            admin_bookings = client.get(
                "/api/v1/admin/bookings",
                headers=platform_admin_headers,
            )
            assert admin_bookings.status_code == 200
            admin_booking = next(row for row in admin_bookings.json() if row["id"] == booking_id)
            assert admin_booking["patient_name"] == "Test patient"
            assert admin_booking["patient_email_masked"] == f"{patient_email[0]}***@example.com"
            assert "patient_email" not in admin_booking

            staff_bookings = client.get("/api/v1/admin/bookings", headers=staff_headers)
            assert staff_bookings.status_code == 200
            assert [row["id"] for row in staff_bookings.json()] == [booking_id]
            assert client.get(
                f"/api/v1/admin/bookings?facility_id={facility_id}",
                headers=other_staff_headers,
            ).status_code == 403

            cancelled = client.post(
                f"/api/v1/admin/bookings/{booking_id}/cancel",
                headers=staff_headers,
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert client.post(
                f"/api/v1/admin/bookings/{booking_id}/cancel",
                headers=staff_headers,
            ).status_code == 409

            users_response = client.get("/api/v1/admin/users", headers=platform_admin_headers)
            assert users_response.status_code == 200
            patient_record = next(row for row in users_response.json() if row["id"] == patient_id)
            assert patient_record["email"] == patient_email
            assert "password_hash" not in patient_record
            assert client.get("/api/v1/admin/users", headers=staff_headers).status_code == 403

            assigned = client.patch(
                f"/api/v1/admin/users/{patient_id}",
                json={"role": "facility_staff", "facility_id": facility_id},
                headers=platform_admin_headers,
            )
            assert assigned.status_code == 200
            assert assigned.json()["role"] == "facility_staff"
            assert assigned.json()["facility_id"] == facility_id

            deactivated = client.patch(
                f"/api/v1/admin/users/{patient_id}",
                json={"is_active": False},
                headers=platform_admin_headers,
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["is_active"] is False
            assert client.get(
                "/api/v1/admin/dashboard",
                headers={"Authorization": f"Bearer invalid"},
            ).status_code == 401
            with SessionLocal() as db:
                account = db.get(User, patient_id)
                assert account is not None
                assert account.token_version == 2
            assert client.patch(
                f"/api/v1/admin/users/{patient_id}",
                json={"role": "platform_admin"},
                headers=platform_admin_headers,
            ).status_code == 422
            assert client.patch(
                f"/api/v1/admin/users/{staff_id}",
                json={"role": "patient"},
                headers=staff_headers,
            ).status_code == 403
        finally:
            if facility_id is not None:
                with SessionLocal() as db:
                    db.query(Booking).filter(Booking.facility_id == facility_id).delete()
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    db.query(AuditEvent).filter(
                        AuditEvent.resource_type == "facility",
                        AuditEvent.resource_id == facility_id,
                    ).delete()
                    facility = db.get(Facility, facility_id)
                    if facility is not None:
                        db.delete(facility)
                    db.commit()
            cleanup_accounts(*account_ids)
