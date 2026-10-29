from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Facility, Service


def test_service_and_facility_search(platform_admin_headers):
    suffix = uuid4().hex[:8]
    facility_name = f"Search Directory Medical Center {suffix}"
    provider_name = f"Dr Search Provider {suffix}"
    service_name = f"Cardiology Consultation {suffix}"
    facility_id = None

    with TestClient(app) as client:
        try:
            facility_response = client.post(
                "/api/v1/facilities",
                json={
                    "name": facility_name,
                    "facility_type": "hospital",
                    "address": "12 Search Street",
                    "city": "Searchville",
                    "phone": "555-0100",
                },
                headers=platform_admin_headers,
            )
            assert facility_response.status_code == 201
            facility_id = facility_response.json()["id"]

            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": service_name,
                    "category": "Cardiology",
                    "service_type": "doctor",
                    "provider_name": provider_name,
                    "fee_paise": 250000,
                },
                headers=platform_admin_headers,
            )
            assert service_response.status_code == 201

            services_response = client.get(
                "/api/v1/services",
                params={"service_type": "doctor", "search": provider_name, "city": "Searchville"},
            )
            assert services_response.status_code == 200
            services = services_response.json()
            assert len(services) == 1
            assert services[0]["facility_id"] == facility_id
            assert services[0]["facility_name"] == facility_name

            global_search_response = client.get(
                "/api/v1/services",
                params={"search": service_name, "city": "Searchville"},
            )
            assert global_search_response.status_code == 200
            assert global_search_response.json()[0]["service_type"] == "doctor"

            facilities_response = client.get("/api/v1/facilities", params={"search": service_name})
            assert facilities_response.status_code == 200
            assert facility_id in [facility["id"] for facility in facilities_response.json()]
        finally:
            if facility_id is not None:
                with SessionLocal() as db:
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    facility = db.get(Facility, facility_id)
                    if facility is not None:
                        db.delete(facility)
                    db.commit()
