import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import and_, exists, func, or_, true
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Facility, FacilityReview, FacilitySubscription, Service
from app.schemas.facility import FacilityCreate, FacilityRead, ServiceCreate, ServiceRead, ServiceSearchRead
from app.schemas.review import FacilityReviewSummary
from app.api.routes.auth import get_current_user
from app.core.audit import record_audit_event
from app.core.config import settings
from app.services.subscriptions import require_facility_entitlement

router = APIRouter(prefix="/facilities", tags=["facilities"])
services_router = APIRouter(prefix="/services", tags=["services"])
MAX_FACILITY_IMAGE_SIZE = 5 * 1024 * 1024
IMAGE_SIGNATURES = (
    ("image/jpeg", b"\xff\xd8\xff"),
    ("image/png", b"\x89PNG\r\n\x1a\n"),
)


async def read_facility_image(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read(MAX_FACILITY_IMAGE_SIZE + 1)
    if len(content) > MAX_FACILITY_IMAGE_SIZE:
        raise HTTPException(413, "Images must be 5 MB or smaller")
    for media_type, signature in IMAGE_SIGNATURES:
        if content.startswith(signature):
            return content, media_type
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return content, "image/webp"
    raise HTTPException(415, "Upload a valid JPEG, PNG, or WebP image")


def image_response(content: bytes | None, media_type: str | None) -> Response:
    if content is None or media_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(404, "Image not found")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


def subscription_is_entitled(now: datetime):
    if not settings.subscriptions_enabled:
        return true()
    subscription = FacilitySubscription
    valid_period = and_(
        subscription.status == "active",
        subscription.current_period_end > now,
    )
    valid_grace = and_(
        subscription.status.in_(("active", "grace_period")),
        subscription.grace_period_end >= now,
    )
    return (
        exists()
        .where(subscription.facility_id == Facility.id)
        .where(or_(valid_period, valid_grace))
    )


@router.get("", response_model=list[FacilityRead])
def list_facilities(
    city: str | None = Query(default=None),
    facility_type: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=180),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=200),
    db: Session = Depends(get_db),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "latitude and longitude must be supplied together")
    now = datetime.now(timezone.utc)
    query = db.query(Facility).filter(
        Facility.is_active.is_(True),
        subscription_is_entitled(now),
    )
    if city:
        query = query.filter(Facility.city.ilike(f"%{city}%"))
    if latitude is not None and longitude is not None:
        lat_delta = radius_km / 110.574
        lon_delta = radius_km / max(1.0, 111.320 * abs(math.cos(math.radians(latitude))))
        query = query.filter(
            Facility.latitude.is_not(None), Facility.longitude.is_not(None),
            Facility.latitude.between(latitude - lat_delta, latitude + lat_delta),
            Facility.longitude.between(longitude - lon_delta, longitude + lon_delta),
        )
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
    if latitude is not None and longitude is not None:
        distance_sq = (
            (Facility.latitude - latitude) * (Facility.latitude - latitude)
            + (Facility.longitude - longitude) * (Facility.longitude - longitude)
            * math.cos(math.radians(latitude)) ** 2
        )
        query = query.order_by(distance_sq, Facility.name, Facility.id)
    else:
        query = query.order_by(Facility.name, Facility.id)
    return query.offset(offset).limit(limit).all()

@services_router.get("", response_model=list[ServiceSearchRead])
def search_services(
    search: str | None = Query(default=None, min_length=1, max_length=180),
    city: str | None = Query(default=None, min_length=1, max_length=100),
    service_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=200),
    db: Session = Depends(get_db),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "latitude and longitude must be supplied together")
    if service_type and service_type not in {"doctor", "diagnostic"}:
        raise HTTPException(422, "service_type must be doctor or diagnostic")

    now = datetime.now(timezone.utc)
    query = db.query(Service, Facility).join(Facility).filter(
        Service.is_active.is_(True),
        Facility.is_active.is_(True),
        subscription_is_entitled(now),
    )
    if service_type:
        query = query.filter(Service.service_type == service_type)
    if city:
        query = query.filter(Facility.city.ilike(f"%{city}%"))
    if latitude is not None and longitude is not None:
        lat_delta = radius_km / 110.574
        lon_delta = radius_km / max(1.0, 111.320 * abs(math.cos(math.radians(latitude))))
        query = query.filter(
            Facility.latitude.is_not(None), Facility.longitude.is_not(None),
            Facility.latitude.between(latitude - lat_delta, latitude + lat_delta),
            Facility.longitude.between(longitude - lon_delta, longitude + lon_delta),
        )
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

    if latitude is not None and longitude is not None:
        distance_sq = (
            (Facility.latitude - latitude) * (Facility.latitude - latitude)
            + (Facility.longitude - longitude) * (Facility.longitude - longitude)
            * math.cos(math.radians(latitude)) ** 2
        )
        query = query.order_by(distance_sq, Service.name, Facility.name, Service.id)
    else:
        query = query.order_by(Service.name, Facility.name, Service.id)

    return [
        {
            **ServiceRead.model_validate(service).model_dump(),
            "facility_name": facility.name,
            "facility_city": facility.city,
            "facility_address": facility.address,
            "facility_phone": facility.phone,
        }
        for service, facility in query
        .offset(offset)
        .limit(limit)
        .all()
    ]

@router.post("", response_model=FacilityRead, status_code=201)
def create_facility(payload: FacilityCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "facility_staff":
        raise HTTPException(403, "Only facility staff can submit a new facility")
    if user.facility_id is not None:
        raise HTTPException(409, "This account is already assigned to a facility")
    facility = Facility(
        **payload.model_dump(),
        is_active=False,
        owner_user_id=user.id,
    )
    db.add(facility)
    db.flush()
    user.facility_id = facility.id
    record_audit_event(db, user, "facility.onboarding_submitted", "facility", facility.id)
    db.commit()
    db.refresh(facility)
    return facility


@router.put("/{facility_id}/image")
async def upload_facility_image(
    facility_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    if user.role != "facility_staff" or user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to update this facility image")
    content, media_type = await read_facility_image(file)
    facility.image_content = content
    facility.image_media_type = media_type
    record_audit_event(db, user, "facility.image_updated", "facility", facility.id)
    db.commit()
    return {"message": "Facility image updated."}


@router.delete("/{facility_id}/image")
def delete_facility_image(
    facility_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    if user.role != "facility_staff" or user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to update this facility image")
    facility.image_content = None
    facility.image_media_type = None
    record_audit_event(db, user, "facility.image_removed", "facility", facility.id)
    db.commit()
    return {"message": "Facility image removed."}


@router.get("/{facility_id}/image")
def get_facility_image(facility_id: int, db: Session = Depends(get_db)):
    facility = db.get(Facility, facility_id)
    if facility is None or not facility.is_active:
        raise HTTPException(404, "Facility not found")
    return image_response(facility.image_content, facility.image_media_type)


@router.put("/{facility_id}/services/{service_id}/image")
async def upload_service_image(
    facility_id: int,
    service_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.facility_id == facility_id)
        .first()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    if user.role != "facility_staff" or user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to update this service image")
    require_facility_entitlement(db, facility_id, operational_write=True)
    content, media_type = await read_facility_image(file)
    service.image_content = content
    service.image_media_type = media_type
    record_audit_event(db, user, "service.image_updated", "service", service.id)
    db.commit()
    return {"message": "Service image updated."}


@router.delete("/{facility_id}/services/{service_id}/image")
def delete_service_image(
    facility_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.facility_id == facility_id)
        .first()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    if user.role != "facility_staff" or user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to update this service image")
    require_facility_entitlement(db, facility_id, operational_write=True)
    service.image_content = None
    service.image_media_type = None
    record_audit_event(db, user, "service.image_removed", "service", service.id)
    db.commit()
    return {"message": "Service image removed."}


@router.get("/{facility_id}/services/{service_id}/image")
def get_service_image(facility_id: int, service_id: int, db: Session = Depends(get_db)):
    service = (
        db.query(Service)
        .join(Facility, Facility.id == Service.facility_id)
        .filter(
            Service.id == service_id,
            Service.facility_id == facility_id,
            Service.is_active.is_(True),
            Facility.is_active.is_(True),
        )
        .first()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    return image_response(service.image_content, service.image_media_type)


@router.get("/{facility_id}/reviews", response_model=FacilityReviewSummary)
def list_facility_reviews(
    facility_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    facility = db.get(Facility, facility_id)
    if facility is None or not facility.is_active:
        raise HTTPException(404, "Facility not found")
    ratings = db.query(
        func.avg(FacilityReview.rating),
        func.count(FacilityReview.id),
    ).filter(FacilityReview.facility_id == facility_id).one()
    reviews = (
        db.query(FacilityReview)
        .filter(FacilityReview.facility_id == facility_id)
        .order_by(FacilityReview.created_at.desc(), FacilityReview.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return FacilityReviewSummary(
        average_rating=round(float(ratings[0]), 1) if ratings[0] is not None else None,
        ratings_count=ratings[1],
        reviews=reviews,
    )


@router.get("/{facility_id}", response_model=FacilityRead)
def get_facility(facility_id: int, db: Session = Depends(get_db)):
    facility = db.get(Facility, facility_id)
    if (
        not facility
        or not facility.is_active
        or not db.query(subscription_is_entitled(datetime.now(timezone.utc))).filter(Facility.id == facility_id).first()
    ):
        raise HTTPException(404, "Facility not found")
    return facility

@router.get("/{facility_id}/services", response_model=list[ServiceRead])
def list_services(
    facility_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    facility = db.get(Facility, facility_id)
    if (
        not facility
        or not facility.is_active
        or not db.query(subscription_is_entitled(datetime.now(timezone.utc))).filter(Facility.id == facility_id).first()
    ):
        raise HTTPException(404, "Facility not found")
    return (
        db.query(Service)
        .filter(Service.facility_id == facility_id, Service.is_active.is_(True))
        .order_by(Service.name, Service.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

@router.post("/{facility_id}/services", response_model=ServiceRead, status_code=201)
def create_service(facility_id: int, payload: ServiceCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    facility = db.get(Facility, facility_id)
    if not facility or not facility.is_active:
        raise HTTPException(404, "Facility not found")
    if user.role != "facility_staff" or user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to manage this facility")
    require_facility_entitlement(db, facility_id, operational_write=True)
    service = Service(facility_id=facility_id, **payload.model_dump())
    db.add(service)
    db.flush()
    record_audit_event(db, user, "service.created", "service", service.id)
    db.commit()
    db.refresh(service)
    return service
