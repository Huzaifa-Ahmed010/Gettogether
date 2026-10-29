from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Facility, Service


def test_assistant_uses_directory_without_external_model(platform_admin_headers):
    suffix = uuid4().hex[:8]
    facility_id = None
    with TestClient(app) as client:
        try:
            facility = client.post(
                "/api/v1/facilities",
                json={
                    "name": f"Navigator Center {suffix}",
                    "facility_type": "diagnostic",
                    "address": "40 Directory Road",
                    "city": f"NavigatorCity{suffix}",
                    "phone": "555-0130",
                },
                headers=platform_admin_headers,
            )
            assert facility.status_code == 201
            facility_id = facility.json()["id"]
            service = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Navigator Blood Test {suffix}",
                    "category": "Laboratory",
                    "service_type": "diagnostic",
                    "provider_name": "",
                    "fee_paise": 10000,
                },
                headers=platform_admin_headers,
            )
            assert service.status_code == 201

            response = client.post(
                "/api/v1/assistant/chat",
                json={"message": f"Where can I find the Navigator Blood Test in NavigatorCity{suffix}?"},
            )
            assert response.status_code == 200
            assert f"Navigator Center {suffix}" in response.json()["reply"]
            assert "can't diagnose" in response.json()["reply"]
        finally:
            if facility_id is not None:
                with SessionLocal() as db:
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    facility = db.get(Facility, facility_id)
                    if facility is not None:
                        db.delete(facility)
                    db.commit()


def test_assistant_handles_emergency_without_diagnosing():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/chat",
            json={"message": "I have chest pain, is this an emergency?"},
        )
    assert response.status_code == 200
    assert "emergency services" in response.json()["reply"]


def test_assistant_has_safe_navigation_fallback_for_unknown_services():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/chat",
            json={"message": f"find a service named {uuid4().hex}"},
        )
    assert response.status_code == 200
    assert "can't diagnose" in response.json()["reply"]
