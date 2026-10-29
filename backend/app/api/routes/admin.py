from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.audit import record_audit_event
from app.db.session import get_db
from app.models import Booking, Facility, Service, User
from app.schemas.admin import (
    AdminBookingRead,
    AdminDashboardRead,
    AdminUserRead,
    FacilityUpdate,
    ServiceUpdate,
    UserAdminUpdate,
)
from app.schemas.facility import FacilityRead, ServiceRead

router = APIRouter(prefix="/admin", tags=["admin"])


def require_directory_access(user: User) -> None:
    if user.role not in {"platform_admin", "facility_staff"}:
        raise HTTPException(403, "Facility management access is required")
    if user.role == "facility_staff" and user.facility_id is None:
        raise HTTPException(403, "This staff account is not assigned to a facility")


def require_facility_access(user: User, facility_id: int) -> None:
    require_directory_access(user)
    if user.role == "facility_staff" and user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to manage this facility")


def require_platform_admin(user: User) -> None:
    if user.role != "platform_admin":
        raise HTTPException(403, "Platform administrator access is required")


def mask_email(email: str) -> str:
    local_part, domain = email.split("@", 1)
    return f"{local_part[:1]}***@{domain}"


@router.get("/dashboard", response_model=AdminDashboardRead)
def get_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_directory_access(user)
    facilities_query = db.query(Facility.id)
    services_query = db.query(Service.id).join(Facility, Service.facility_id == Facility.id)
    bookings_query = db.query(Booking.id)
    if user.role == "facility_staff":
        facilities_query = facilities_query.filter(Facility.id == user.facility_id)
        services_query = services_query.filter(Facility.id == user.facility_id)
        bookings_query = bookings_query.filter(Booking.facility_id == user.facility_id)
        users_count = None
    else:
        users_count = db.query(User.id).count()
    return AdminDashboardRead(
        facilities=facilities_query.filter(Facility.is_active.is_(True)).count(),
        services=services_query.filter(
            Service.is_active.is_(True),
            Facility.is_active.is_(True),
        ).count(),
        bookings=bookings_query.count(),
        users=users_count,
    )


@router.get("/facilities", response_model=list[FacilityRead])
def list_managed_facilities(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_directory_access(user)
    query = db.query(Facility)
    if user.role == "facility_staff":
        query = query.filter(Facility.id == user.facility_id)
    return query.order_by(Facility.name).all()


@router.patch("/facilities/{facility_id}", response_model=FacilityRead)
def update_facility(
    facility_id: int,
    payload: FacilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_facility_access(user, facility_id)
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    changes = payload.model_dump(exclude_unset=True)
    if user.role == "facility_staff" and "is_active" in changes:
        raise HTTPException(403, "Only platform administrators can activate or deactivate facilities")
    for field, value in changes.items():
        setattr(facility, field, value)
    db.flush()
    record_audit_event(db, user, "facility.updated", "facility", facility.id)
    db.commit()
    db.refresh(facility)
    return facility


@router.get("/facilities/{facility_id}/services", response_model=list[ServiceRead])
def list_managed_services(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_facility_access(user, facility_id)
    if db.get(Facility, facility_id) is None:
        raise HTTPException(404, "Facility not found")
    return (
        db.query(Service)
        .filter(Service.facility_id == facility_id)
        .order_by(Service.name)
        .all()
    )


@router.patch(
    "/facilities/{facility_id}/services/{service_id}",
    response_model=ServiceRead,
)
def update_service(
    facility_id: int,
    service_id: int,
    payload: ServiceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_facility_access(user, facility_id)
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.facility_id == facility_id,
    ).first()
    if service is None:
        raise HTTPException(404, "Service not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.flush()
    record_audit_event(db, user, "service.updated", "service", service.id)
    db.commit()
    db.refresh(service)
    return service


@router.get("/bookings", response_model=list[AdminBookingRead])
def list_managed_bookings(
    status: Literal["booked", "verified", "cancelled"] | None = None,
    facility_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_directory_access(user)
    query = (
        db.query(Booking, Facility.name, Service.name)
        .join(Facility, Booking.facility_id == Facility.id)
        .join(Service, Booking.service_id == Service.id)
    )
    if user.role == "facility_staff":
        if facility_id is not None and facility_id != user.facility_id:
            raise HTTPException(403, "You are not authorized to view bookings for this facility")
        query = query.filter(Booking.facility_id == user.facility_id)
    elif facility_id is not None:
        query = query.filter(Booking.facility_id == facility_id)
    if status:
        query = query.filter(Booking.status == status)
    rows = query.order_by(Booking.appointment_at.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": booking.id,
            "facility_id": booking.facility_id,
            "service_id": booking.service_id,
            "appointment_at": booking.appointment_at,
            "payment_method": booking.payment_method,
            "payment_status": booking.payment_status,
            "status": booking.status,
            "patient_name": booking.patient_name,
            "patient_email_masked": mask_email(booking.patient_email),
            "facility_name": facility_name,
            "service_name": service_name,
        }
        for booking, facility_name, service_name in rows
    ]


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingRead)
def cancel_managed_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_directory_access(user)
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if booking is None:
        raise HTTPException(404, "Booking not found")
    require_facility_access(user, booking.facility_id)
    appointment_at = booking.appointment_at
    if appointment_at.tzinfo is None:
        appointment_at = appointment_at.replace(tzinfo=timezone.utc)
    if appointment_at <= datetime.now(timezone.utc):
        raise HTTPException(409, "Past appointments cannot be cancelled")
    if booking.status != "booked":
        raise HTTPException(409, "This booking can no longer be cancelled")
    booking.status = "cancelled"
    record_audit_event(db, user, "booking.cancelled", "booking", booking.id)
    db.commit()
    db.refresh(booking)
    facility = db.get(Facility, booking.facility_id)
    service = db.get(Service, booking.service_id)
    return {
        "id": booking.id,
        "facility_id": booking.facility_id,
        "service_id": booking.service_id,
        "appointment_at": booking.appointment_at,
        "payment_method": booking.payment_method,
        "payment_status": booking.payment_status,
        "status": booking.status,
        "patient_name": booking.patient_name,
        "patient_email_masked": mask_email(booking.patient_email),
        "facility_name": facility.name,
        "service_name": service.name,
    }


@router.get("/users", response_model=list[AdminUserRead])
def list_managed_users(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    query = db.query(User, Facility.name).outerjoin(Facility, User.facility_id == Facility.id)
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    rows = query.order_by(User.created_at.desc(), User.id.desc()).all()
    return [
        {
            **AdminUserRead.model_validate(account).model_dump(),
            "facility_name": facility_name,
        }
        for account, facility_name in rows
    ]


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_managed_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    account = db.get(User, user_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    if account.role == "platform_admin":
        raise HTTPException(409, "Platform administrator accounts cannot be changed in the dashboard")
    changes = payload.model_dump(exclude_unset=True)
    if account.id == user.id and (
        changes.get("is_active") is False
        or "role" in changes
        or "facility_id" in changes
    ):
        raise HTTPException(409, "You cannot disable or change your own account access")

    next_role = changes.get("role", account.role)
    next_facility_id = changes.get("facility_id", account.facility_id)
    if next_role == "facility_staff":
        if next_facility_id is None:
            raise HTTPException(422, "Assigning facility staff requires a facility_id")
        facility = db.get(Facility, next_facility_id)
        if facility is None or not facility.is_active:
            raise HTTPException(422, "The assigned facility must exist and be active")
        if not account.email_verified:
            raise HTTPException(409, "The account must be verified before staff assignment")
    elif next_role == "patient":
        next_facility_id = None

    changed = False
    for field, value in changes.items():
        if field == "facility_id":
            continue
        if getattr(account, field) != value:
            setattr(account, field, value)
            changed = True
    if account.facility_id != next_facility_id:
        account.facility_id = next_facility_id
        changed = True
    if changed:
        account.token_version += 1
        db.flush()
        record_audit_event(db, user, "account.updated", "user", account.id)
        db.commit()
        db.refresh(account)
    facility_name = None
    if account.facility_id is not None:
        facility = db.get(Facility, account.facility_id)
        facility_name = facility.name if facility else None
    return {
        **AdminUserRead.model_validate(account).model_dump(),
        "facility_name": facility_name,
    }
