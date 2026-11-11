from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Facility, Service, User


def test_service_and_facility_search(
    platform_admin_headers,
    account_factory,
    grant_facility_entitlement,
):
    suffix = uuid4().hex[:8]
    facility_name = f"Search Directory Medical Center {suffix}"
    provider_name = f"Dr Search Provider {suffix}"
    service_name = f"Cardiology Consultation {suffix}"
    facility_id = None

    with TestClient(app) as client:
        try:
            _, staff_headers = account_factory("facility_staff")
            facility_response = client.post(
                "/api/v1/facilities",
                json={
                    "name": facility_name,
                    "facility_type": "hospital",
                    "address": "12 Search Street",
                    "city": "Searchville",
                    "phone": "555-0100",
                },
                headers=staff_headers,
            )
            assert facility_response.status_code == 201
            facility_id = facility_response.json()["id"]
            assert client.patch(
                f"/api/v1/admin/facilities/{facility_id}",
                json={"is_active": True},
                headers=platform_admin_headers,
            ).status_code == 200
            grant_facility_entitlement(facility_id)

            service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": service_name,
                    "category": "Cardiology",
                    "service_type": "doctor",
                    "provider_name": provider_name,
                    "fee_paise": 250000,
                },
                headers=staff_headers,
            )
            assert service_response.status_code == 201
            second_service_response = client.post(
                f"/api/v1/facilities/{facility_id}/services",
                json={
                    "name": f"Cardiology Follow-up {suffix}",
                    "category": "Cardiology",
                    "service_type": "doctor",
                    "provider_name": f"Dr Another Provider {suffix}",
                    "fee_paise": 150000,
                },
                headers=staff_headers,
            )
            assert second_service_response.status_code == 201

            services_response = client.get(
                "/api/v1/services",
                params={"service_type": "doctor", "search": provider_name, "city": "Searchville"},
            )
            assert services_response.status_code == 200
            services = services_response.json()
            assert len(services) == 1
            assert services[0]["facility_id"] == facility_id
            assert services[0]["facility_name"] == facility_name

            first_search_page = client.get(
                "/api/v1/services",
                params={"search": "Cardiology", "city": "Searchville", "limit": 1, "offset": 0},
            )
            second_search_page = client.get(
                "/api/v1/services",
                params={"search": "Cardiology", "city": "Searchville", "limit": 1, "offset": 1},
            )
            assert first_search_page.status_code == second_search_page.status_code == 200
            assert len(first_search_page.json()) == len(second_search_page.json()) == 1
            assert first_search_page.json()[0]["id"] != second_search_page.json()[0]["id"]

            global_search_response = client.get(
                "/api/v1/services",
                params={"search": service_name, "city": "Searchville"},
            )
            assert global_search_response.status_code == 200
            assert global_search_response.json()[0]["service_type"] == "doctor"

            facilities_response = client.get("/api/v1/facilities", params={"search": service_name})
            assert facilities_response.status_code == 200
            assert facility_id in [facility["id"] for facility in facilities_response.json()]
            facility_page = client.get(
                "/api/v1/facilities",
                params={"search": service_name, "limit": 1, "offset": 0},
            )
            assert facility_page.status_code == 200
            assert len(facility_page.json()) == 1

            assert client.get(
                "/api/v1/services",
                params={"search": service_name, "limit": 101},
            ).status_code == 422
            first_service_page = client.get(
                f"/api/v1/facilities/{facility_id}/services",
                params={"limit": 1, "offset": 0},
            )
            second_service_page = client.get(
                f"/api/v1/facilities/{facility_id}/services",
                params={"limit": 1, "offset": 1},
            )
            assert first_service_page.status_code == second_service_page.status_code == 200
            assert len(first_service_page.json()) == len(second_service_page.json()) == 1
            assert first_service_page.json()[0]["id"] != second_service_page.json()[0]["id"]
            assert client.get(
                f"/api/v1/facilities/{facility_id}/services",
                params={"limit": 0},
            ).status_code == 422

            deactivated = client.patch(
                f"/api/v1/admin/facilities/{facility_id}",
                json={"is_active": False},
                headers=platform_admin_headers,
            )
            assert deactivated.status_code == 200
            assert client.get(f"/api/v1/facilities/{facility_id}").status_code == 404
            assert client.get(f"/api/v1/facilities/{facility_id}/services").status_code == 404
            assert client.get(
                "/api/v1/services",
                params={"search": service_name},
            ).json() == []
        finally:
            if facility_id is not None:
                with SessionLocal() as db:
                    db.query(Service).filter(Service.facility_id == facility_id).delete()
                    db.query(User).filter(User.facility_id == facility_id).update(
                        {User.facility_id: None},
                        synchronize_session=False,
                    )
                    facility = db.get(Facility, facility_id)
                    if facility is not None:
                        db.delete(facility)
                    db.commit()
