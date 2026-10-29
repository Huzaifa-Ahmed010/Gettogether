import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.audit import record_audit_event
from app.core.config import settings
from app.db.session import get_db
from app.models import Booking, Facility, Service, User
from app.schemas.booking import BookingCreate, BookingCreated, BookingRead, BookingSummary, VerifyRead, VerifyRequest

router = APIRouter(prefix="/bookings", tags=["bookings"])


def hash_booking_code(code: str) -> str:
    return hmac.new(settings.secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def new_code(db: Session) -> str:
    for _ in range(10):
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hash_booking_code(code)
        if not db.query(Booking.id).filter(Booking.verification_code == code_hash).first():
            return code
    raise HTTPException(503, "Could not issue a booking code; please retry")


def require_facility_access(user: User, facility_id: int) -> None:
    if user.role == "platform_admin":
        return
    if user.role == "facility_staff" and user.facility_id == facility_id:
        return
    raise HTTPException(403, "You are not authorized to manage bookings for this facility")


@router.post("", response_model=BookingCreated, status_code=201)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    facility = db.get(Facility, payload.facility_id)
    service = db.get(Service, payload.service_id)
    if not facility or not facility.is_active:
        raise HTTPException(404, "Facility not found or inactive")
    if not service or not service.is_active or service.facility_id != facility.id:
        raise HTTPException(422, "Service does not belong to the selected facility")
    if payload.appointment_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Appointment must be in the future")
    if payload.payment_method != "physical":
        raise HTTPException(422, "Only payment at the facility is currently available")

    code = new_code(db)
    booking = Booking(
        patient_name=user.name,
        patient_email=user.email,
        facility_id=facility.id,
        service_id=service.id,
        appointment_at=payload.appointment_at,
        payment_method="physical",
        payment_status="unpaid",
        verification_code=hash_booking_code(code),
    )
    db.add(booking)
    try:
        db.flush()
        record_audit_event(db, user, "booking.created", "booking", booking.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(503, "Could not create booking; please retry")
    db.refresh(booking)
    return BookingCreated(
        id=booking.id,
        facility_id=booking.facility_id,
        service_id=booking.service_id,
        appointment_at=booking.appointment_at,
        payment_method=booking.payment_method,
        payment_status=booking.payment_status,
        status=booking.status,
        verification_code=code,
    )


@router.get("", response_model=list[BookingSummary])
def list_my_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(Booking, Facility.name, Service.name)
        .join(Facility, Booking.facility_id == Facility.id)
        .join(Service, Booking.service_id == Service.id)
        .filter(Booking.patient_email == user.email)
        .order_by(Booking.appointment_at.desc())
        .all()
    )
    return [
        {
            **BookingRead.model_validate(booking).model_dump(),
            "facility_name": facility_name,
            "service_name": service_name,
        }
        for booking, facility_name, service_name in rows
    ]


@router.get("/{booking_id}", response_model=BookingRead)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.patient_email != user.email:
        require_facility_access(user, booking.facility_id)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if not booking or booking.patient_email != user.email:
        raise HTTPException(404, "Booking not found")
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
    return booking


@router.post("/verify", response_model=VerifyRead)
def verify_code(
    payload: VerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in {"platform_admin", "facility_staff"}:
        raise HTTPException(403, "Facility staff access is required to verify bookings")
    booking = (
        db.query(Booking)
        .filter(Booking.verification_code == hash_booking_code(payload.code))
        .with_for_update()
        .first()
    )
    if not booking:
        return VerifyRead(valid=False, message="Invalid booking code")
    require_facility_access(user, booking.facility_id)
    if booking.status == "verified":
        return VerifyRead(valid=False, message="Booking code has already been used", booking_id=booking.id,
                          payment_status=booking.payment_status, appointment_at=booking.appointment_at)
    if booking.status != "booked":
        return VerifyRead(valid=False, message="Booking is not active", booking_id=booking.id,
                          payment_status=booking.payment_status, appointment_at=booking.appointment_at)
    booking.status = "verified"
    booking.verified_at = datetime.now(timezone.utc)
    record_audit_event(db, user, "booking.verified", "booking", booking.id)
    db.commit()
    return VerifyRead(valid=True, message="Booking verified", booking_id=booking.id,
                      payment_status=booking.payment_status, appointment_at=booking.appointment_at)
