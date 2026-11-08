import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.audit import record_audit_event
from app.core.config import settings
from app.db.session import get_db
from app.models import Booking, BookingDocument, Facility, Service, User
from app.schemas.booking import (
    BookingCreate,
    BookingCreated,
    BookingDocumentRead,
    BookingRead,
    BookingSummary,
    PaymentCollectionRequest,
    VerifyRead,
    VerifyRequest,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_DOCUMENTS_PER_BOOKING = 5
DOCUMENT_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


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


def require_document_access(user: User, booking: Booking) -> None:
    if user.role == "patient" and booking.patient_user_id == user.id:
        return
    if user.role == "facility_staff" and user.facility_id == booking.facility_id:
        return
    raise HTTPException(404, "Booking not found")


def safe_document_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]", "_", basename)[:255] or "document"


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
        patient_user_id=user.id,
        patient_name=user.name,
        patient_email=user.email,
        facility_id=facility.id,
        service_id=service.id,
        appointment_at=payload.appointment_at,
        payment_method="physical",
        payment_status="unpaid" if service.fee_paise else "not_required",
        payment_due_paise=service.fee_paise,
        payment_currency="INR",
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
        payment_due_paise=booking.payment_due_paise,
        payment_amount_paise=booking.payment_amount_paise,
        payment_currency=booking.payment_currency,
        payment_collected_at=booking.payment_collected_at,
        payment_reference=booking.payment_reference,
        status=booking.status,
        verification_code=code,
    )


@router.post("/{booking_id}/documents", response_model=list[BookingDocumentRead], status_code=201)
def upload_booking_documents(
    booking_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = (
        db.query(Booking)
        .filter(
            Booking.id == booking_id,
            Booking.patient_user_id == user.id,
        )
        .with_for_update()
        .first()
    )
    if booking is None:
        raise HTTPException(404, "Booking not found")
    if booking.status != "booked":
        raise HTTPException(409, "Documents can only be uploaded to an active appointment request")
    if not files:
        raise HTTPException(422, "Select at least one document to upload")
    existing_count = db.query(BookingDocument.id).filter(
        BookingDocument.booking_id == booking.id
    ).count()
    if existing_count + len(files) > MAX_DOCUMENTS_PER_BOOKING:
        raise HTTPException(
            413,
            f"A maximum of {MAX_DOCUMENTS_PER_BOOKING} documents is allowed per appointment.",
        )

    pending_documents: list[BookingDocument] = []
    for upload in files:
        filename = safe_document_filename(upload.filename or "")
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        document_type = DOCUMENT_TYPES.get(extension)
        if document_type is None:
            raise HTTPException(415, "Only PDF, JPEG, and PNG documents are accepted")
        media_type, signature = document_type
        content = upload.file.read(MAX_DOCUMENT_SIZE + 1)
        if len(content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(413, "Each document must be 10 MB or smaller")
        if not content.startswith(signature):
            raise HTTPException(422, f"{filename} does not match its file type")
        if upload.content_type not in {media_type, "application/octet-stream"}:
            raise HTTPException(415, f"{filename} has an unsupported content type")
        pending_documents.append(
            BookingDocument(
                booking_id=booking.id,
                uploaded_by_user_id=user.id,
                filename=filename,
                media_type=media_type,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                content=content,
            )
        )

    db.add_all(pending_documents)
    db.flush()
    record_audit_event(db, user, "booking.documents_uploaded", "booking", booking.id)
    db.commit()
    for document in pending_documents:
        db.refresh(document)
    return pending_documents


@router.get("/{booking_id}/documents", response_model=list[BookingDocumentRead])
def list_booking_documents(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    require_document_access(user, booking)
    documents = (
        db.query(BookingDocument)
        .filter(BookingDocument.booking_id == booking.id)
        .order_by(BookingDocument.uploaded_at, BookingDocument.id)
        .all()
    )
    record_audit_event(db, user, "booking.documents_listed", "booking", booking.id)
    db.commit()
    return documents


@router.get("/{booking_id}/documents/{document_id}")
def download_booking_document(
    booking_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    require_document_access(user, booking)
    document = (
        db.query(BookingDocument)
        .filter(
            BookingDocument.id == document_id,
            BookingDocument.booking_id == booking.id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    record_audit_event(db, user, "booking.document_downloaded", "booking_document", document.id)
    db.commit()
    return Response(
        content=document.content,
        media_type=document.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("", response_model=list[BookingSummary])
def list_my_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(Booking, Facility.name, Service.name, Service.provider_name)
        .join(Facility, Booking.facility_id == Facility.id)
        .join(Service, Booking.service_id == Service.id)
        .filter(Booking.patient_user_id == user.id)
        .order_by(Booking.appointment_at.desc(), Booking.id.desc())
        .all()
    )
    return [
        {
            **BookingRead.model_validate(booking).model_dump(),
            "facility_name": facility_name,
            "service_name": service_name,
            "provider_name": provider_name,
        }
        for booking, facility_name, service_name, provider_name in rows
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
    if booking.patient_user_id != user.id:
        require_facility_access(user, booking.facility_id)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if not booking or booking.patient_user_id != user.id:
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


@router.post("/{booking_id}/payment", response_model=BookingRead)
def record_physical_payment(
    booking_id: int,
    payload: PaymentCollectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in {"platform_admin", "facility_staff"}:
        raise HTTPException(403, "Facility staff access is required to record payments")
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if booking is None:
        raise HTTPException(404, "Booking not found")
    require_facility_access(user, booking.facility_id)
    if booking.status != "booked":
        raise HTTPException(409, "Payment can only be recorded for an active booking")
    if booking.payment_status != "unpaid":
        raise HTTPException(409, "Payment has already been recorded or is not required")
    if booking.payment_due_paise <= 0:
        raise HTTPException(409, "No payment is due for this booking")

    booking.payment_amount_paise = booking.payment_due_paise
    booking.payment_status = "paid"
    booking.payment_collected_by_user_id = user.id
    booking.payment_collected_at = datetime.now(timezone.utc)
    booking.payment_reference = payload.reference
    record_audit_event(db, user, "booking.payment_collected", "booking", booking.id)
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
    appointment_at = booking.appointment_at
    if appointment_at.tzinfo is None:
        appointment_at = appointment_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if now < appointment_at - timedelta(minutes=30):
        return VerifyRead(
            valid=False,
            message="Check-in opens 30 minutes before the appointment.",
            booking_id=booking.id,
            payment_status=booking.payment_status,
            appointment_at=booking.appointment_at,
        )
    if now > appointment_at + timedelta(minutes=60):
        return VerifyRead(
            valid=False,
            message="The check-in window has closed.",
            booking_id=booking.id,
            payment_status=booking.payment_status,
            appointment_at=booking.appointment_at,
        )
    if booking.payment_status == "unpaid":
        return VerifyRead(
            valid=False,
            message="Record the pay-at-facility payment before checking in.",
            booking_id=booking.id,
            payment_status=booking.payment_status,
            appointment_at=booking.appointment_at,
        )
    booking.status = "verified"
    booking.verified_at = datetime.now(timezone.utc)
    record_audit_event(db, user, "booking.verified", "booking", booking.id)
    db.commit()
    return VerifyRead(valid=True, message="Booking verified", booking_id=booking.id,
                      payment_status=booking.payment_status, appointment_at=booking.appointment_at)
