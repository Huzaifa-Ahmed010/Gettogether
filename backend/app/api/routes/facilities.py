from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Facility, Service
from app.schemas.facility import FacilityCreate, FacilityRead, ServiceCreate, ServiceRead, ServiceSearchRead
from app.api.routes.auth import get_current_user
from app.core.audit import record_audit_event

router = APIRouter(prefix="/facilities", tags=["facilities"])
services_router = APIRouter(prefix="/services", tags=["services"])

@router.get("", response_model=list[FacilityRead])
def list_facilities(
    city: str | None = Query(default=None),
    facility_type: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=180),
    db: Session = Depends(get_db),
):
    query = db.query(Facility).filter(Facility.is_active.is_(True))
    if city:
        query = query.filter(Facility.city.ilike(f"%{city}%"))
    if facility_type:
        if facility_type not in {"hospital", "diagnostic"}:
            raise HTTPException(422, "facility_type must be hospital or diagnostic")
        query = query.filter(Facility.facility_type == facility_type)
    if search:
        term = f"%{search}%"
        matching_services = db.query(Service.id).filter(
            Service.facility_id == Facility.id,
            Service.is_active.is_(True),
            or_(
                Service.name.ilike(term),
                Service.category.ilike(term),
                Service.provider_name.ilike(term),
            ),
        ).exists()
        query = query.filter(
            or_(
                Facility.name.ilike(term),
                Facility.address.ilike(term),
                Facility.city.ilike(term),
                matching_services,
            )
        )
    return query.order_by(Facility.name).all()

@services_router.get("", response_model=list[ServiceSearchRead])
def search_services(
    search: str | None = Query(default=None, min_length=1, max_length=180),
    city: str | None = Query(default=None, min_length=1, max_length=100),
    service_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if service_type and service_type not in {"doctor", "diagnostic"}:
        raise HTTPException(422, "service_type must be doctor or diagnostic")

    query = db.query(Service, Facility).join(Facility).filter(
        Service.is_active.is_(True),
        Facility.is_active.is_(True),
    )
    if service_type:
        query = query.filter(Service.service_type == service_type)
    if city:
        query = query.filter(Facility.city.ilike(f"%{city}%"))
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Service.name.ilike(term),
                Service.category.ilike(term),
                Service.provider_name.ilike(term),
                Facility.name.ilike(term),
                Facility.city.ilike(term),
                Facility.address.ilike(term),
            )
        )

    return [
        {
            **ServiceRead.model_validate(service).model_dump(),
            "facility_name": facility.name,
            "facility_city": facility.city,
            "facility_address": facility.address,
            "facility_phone": facility.phone,
        }
        for service, facility in query.order_by(Service.name, Facility.name).all()
    ]

@router.post("", response_model=FacilityRead, status_code=201)
def create_facility(payload: FacilityCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "platform_admin":
        raise HTTPException(403, "Platform administrator access is required")
    facility = Facility(**payload.model_dump())
    db.add(facility)
    db.flush()
    record_audit_event(db, user, "facility.created", "facility", facility.id)
    db.commit()
    db.refresh(facility)
    return facility

@router.get("/{facility_id}", response_model=FacilityRead)
def get_facility(facility_id: int, db: Session = Depends(get_db)):
    facility = db.get(Facility, facility_id)
    if not facility or not facility.is_active:
        raise HTTPException(404, "Facility not found")
    return facility

@router.get("/{facility_id}/services", response_model=list[ServiceRead])
def list_services(facility_id: int, db: Session = Depends(get_db)):
    if not db.get(Facility, facility_id):
        raise HTTPException(404, "Facility not found")
    return db.query(Service).filter(Service.facility_id == facility_id, Service.is_active.is_(True)).order_by(Service.name).all()

@router.post("/{facility_id}/services", response_model=ServiceRead, status_code=201)
def create_service(facility_id: int, payload: ServiceCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    facility = db.get(Facility, facility_id)
    if not facility or not facility.is_active:
        raise HTTPException(404, "Facility not found")
    if user.role != "platform_admin" and not (
        user.role == "facility_staff" and user.facility_id == facility_id
    ):
        raise HTTPException(403, "You are not authorized to manage this facility")
    service = Service(facility_id=facility_id, **payload.model_dump())
    db.add(service)
    db.flush()
    record_audit_event(db, user, "service.created", "service", service.id)
    db.commit()
    db.refresh(service)
    return service
