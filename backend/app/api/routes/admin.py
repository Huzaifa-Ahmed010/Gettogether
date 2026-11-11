from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.booking_code_delivery import encrypt_booking_code
from app.api.routes.auth import get_current_user
from app.api.routes.bookings import hash_booking_code, new_code
from app.core.audit import record_audit_event
from app.db.session import get_db
from app.models import (
    AuditEvent,
    Booking,
    Facility,
    FacilitySubscription,
    PaymentWebhookEvent,
    Service,
    SubscriptionPayment,
    SubscriptionPlan,
    User,
)
from app.schemas.admin import (
    AdminBookingRead,
    AdminDashboardRead,
    AdminUserRead,
    FacilityUpdate,
    ServiceUpdate,
    UserAdminUpdate,
)
from app.schemas.booking import BookingDecisionRequest
from app.schemas.facility import FacilityRead, ServiceRead
from app.schemas.subscription import (
    AdminSubscriptionPaymentRead,
    AdminSubscriptionExtension,
    AuditEventRead,
    FacilityOwnerUpdate,
    PaymentWebhookEventRead,
    PlatformSubscriptionRead,
    SubscriptionPlanCreate,
    SubscriptionPlanRead,
    SubscriptionPlanUpdate,
)
from app.services.subscriptions import (
    effective_subscription_status,
    refresh_subscription_state,
    require_facility_entitlement,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_directory_access(user: User) -> None:
    if user.role not in {"platform_admin", "facility_staff"}:
        raise HTTPException(403, "Facility management access is required")


def require_staff_facility_access(user: User, facility_id: int | None = None) -> None:
    if user.role != "facility_staff" or user.facility_id is None:
        raise HTTPException(403, "Facility staff access is required")
    if facility_id is not None and user.facility_id != facility_id:
        raise HTTPException(403, "You are not authorized to manage this facility")


def require_platform_admin(user: User) -> None:
    if user.role != "platform_admin":
        raise HTTPException(403, "Platform administrator access is required")


def mask_email(email: str) -> str:
    local_part, domain = email.split("@", 1)
    return f"{local_part[:1]}***@{domain}"


def managed_booking_data(db: Session, booking: Booking) -> dict:
    facility = db.get(Facility, booking.facility_id)
    service = db.get(Service, booking.service_id)
    collector = (
        db.get(User, booking.payment_collected_by_user_id)
        if booking.payment_collected_by_user_id is not None
        else None
    )
    if facility is None or service is None:
        raise HTTPException(409, "Appointment directory records are unavailable")
    return {
        "id": booking.id,
        "facility_id": booking.facility_id,
        "service_id": booking.service_id,
        "appointment_at": booking.appointment_at,
        "payment_method": booking.payment_method,
        "payment_status": booking.payment_status,
        "payment_due_paise": booking.payment_due_paise,
        "payment_amount_paise": booking.payment_amount_paise,
        "payment_currency": booking.payment_currency,
        "payment_collected_at": booking.payment_collected_at,
        "payment_collected_by_user_id": booking.payment_collected_by_user_id,
        "payment_collector_name": collector.name if collector else None,
        "payment_reference": booking.payment_reference,
        "status": booking.status,
        "rejection_reason": booking.rejection_reason,
        "patient_name": booking.patient_name,
        "patient_email_masked": mask_email(booking.patient_email),
        "facility_name": facility.name,
        "service_name": service.name,
        "provider_name": service.provider_name,
    }


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
    changes = payload.model_dump(exclude_unset=True)
    if user.role == "platform_admin":
        if any(field != "is_active" for field in changes):
            raise HTTPException(
                403,
                "Platform administrators can only activate or deactivate facilities",
            )
    else:
        require_staff_facility_access(user, facility_id)
        require_facility_entitlement(db, facility_id, operational_write=True)
    if user.role == "facility_staff" and "is_active" in changes:
        raise HTTPException(403, "Only platform administrators can activate or deactivate facilities")
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    for field, value in changes.items():
        setattr(facility, field, value)
    db.flush()
    record_audit_event(db, user, "facility.updated", "facility", facility.id)
    db.commit()
    db.refresh(facility)
    return facility


@router.post("/facilities/{facility_id}/owner")
def transfer_facility_owner(
    facility_id: int,
    payload: FacilityOwnerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    facility = db.get(Facility, facility_id)
    account = db.get(User, payload.user_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    if (
        account is None
        or not account.is_active
        or account.role != "facility_staff"
        or account.facility_id != facility.id
    ):
        raise HTTPException(422, "The billing owner must be an active facility-staff account assigned to this facility")
    previous_owner_id = facility.owner_user_id
    facility.owner_user_id = account.id
    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.facility_id == facility.id)
        .with_for_update()
        .first()
    )
    if subscription is not None:
        subscription.billing_contact_user_id = account.id
    record_audit_event(
        db,
        user,
        "facility.billing_owner_transferred",
        "facility",
        facility.id,
        details=f"Billing owner changed from user {previous_owner_id} to user {account.id}.",
    )
    db.commit()
    return {
        "message": "Facility billing owner updated.",
        "previous_owner_user_id": previous_owner_id,
        "owner_user_id": account.id,
    }


@router.get("/facilities/{facility_id}/staff", response_model=list[AdminUserRead])
def list_facility_staff_accounts(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    accounts = (
        db.query(User)
        .filter(
            User.facility_id == facility_id,
            User.role == "facility_staff",
            User.is_active.is_(True),
        )
        .order_by(User.name, User.id)
        .all()
    )
    return [
        {
            **AdminUserRead.model_validate(account).model_dump(),
            "facility_name": facility.name,
        }
        for account in accounts
    ]


@router.delete("/facilities/{facility_id}")
def delete_facility(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    facility = db.query(Facility).filter(Facility.id == facility_id).with_for_update().first()
    if facility is None:
        raise HTTPException(404, "Facility not found")
    if db.query(Booking.id).filter(Booking.facility_id == facility_id).first():
        raise HTTPException(
            409,
            "This facility has bookings and cannot be deleted. Deactivate it to keep its booking history.",
        )
    if db.query(User.id).filter(User.facility_id == facility_id).first():
        raise HTTPException(
            409,
            "Staff are assigned to this facility. Reassign them before deleting it.",
        )

    services = db.query(Service).filter(Service.facility_id == facility_id).all()
    try:
        for service in services:
            record_audit_event(db, user, "service.deleted", "service", service.id)
            db.delete(service)
        record_audit_event(db, user, "facility.deleted", "facility", facility.id)
        db.delete(facility)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409,
            "This facility is linked to existing records and cannot be deleted. Deactivate it instead.",
        ) from error
    return {"message": "Facility deleted."}


@router.get("/facilities/{facility_id}/services", response_model=list[ServiceRead])
def list_managed_services(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user, facility_id)
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
    require_staff_facility_access(user, facility_id)
    if user.role == "facility_staff":
        require_staff_facility_access(user, facility_id)
        require_facility_entitlement(db, facility_id, operational_write=True)
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


@router.delete("/facilities/{facility_id}/services/{service_id}")
def delete_service(
    facility_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user, facility_id)
    require_facility_entitlement(db, facility_id, operational_write=True)
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.facility_id == facility_id)
        .with_for_update()
        .first()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    if db.query(Booking.id).filter(Booking.service_id == service_id).first():
        raise HTTPException(
            409,
            "This service has bookings and cannot be deleted. Deactivate it to keep its booking history.",
        )
    record_audit_event(db, user, "service.deleted", "service", service.id)
    db.delete(service)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409,
            "This service is linked to existing records and cannot be deleted. Deactivate it instead.",
        ) from error
    return {"message": "Service deleted."}


@router.get("/bookings", response_model=list[AdminBookingRead])
def list_managed_bookings(
    status: Literal[
        "requested", "confirmed", "rejected", "cancelled", "checked_in", "completed"
    ] | None = None,
    facility_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user)
    query = (
        db.query(Booking, Facility.name, Service.name, Service.provider_name)
        .join(Facility, Booking.facility_id == Facility.id)
        .join(Service, Booking.service_id == Service.id)
        .outerjoin(User, Booking.payment_collected_by_user_id == User.id)
    )
    if facility_id is not None and facility_id != user.facility_id:
        raise HTTPException(403, "You are not authorized to view bookings for this facility")
    query = query.filter(Booking.facility_id == user.facility_id)
    if status:
        query = query.filter(Booking.status == status)
    rows = query.with_entities(
        Booking,
        Facility.name,
        Service.name,
        Service.provider_name,
        User.name,
    ).order_by(Booking.appointment_at.desc()).offset(offset).limit(limit).all()
    for booking, _, _, _, _ in rows:
        record_audit_event(db, user, "booking.viewed", "booking", booking.id)
    if rows:
        db.commit()
    return [
        {
            "id": booking.id,
            "facility_id": booking.facility_id,
            "service_id": booking.service_id,
            "appointment_at": booking.appointment_at,
            "payment_method": booking.payment_method,
            "payment_status": booking.payment_status,
            "payment_due_paise": booking.payment_due_paise,
            "payment_amount_paise": booking.payment_amount_paise,
            "payment_currency": booking.payment_currency,
            "payment_collected_at": booking.payment_collected_at,
            "payment_collected_by_user_id": booking.payment_collected_by_user_id,
            "payment_collector_name": collector_name,
            "payment_reference": booking.payment_reference,
            "status": booking.status,
            "rejection_reason": booking.rejection_reason,
            "patient_name": booking.patient_name,
            "patient_email_masked": mask_email(booking.patient_email),
            "facility_name": facility_name,
            "service_name": service_name,
            "provider_name": provider_name,
        }
        for booking, facility_name, service_name, provider_name, collector_name in rows
    ]


@router.post("/bookings/{booking_id}/confirm", response_model=AdminBookingRead)
def confirm_managed_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user)
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if booking is None:
        raise HTTPException(404, "Appointment not found")
    require_staff_facility_access(user, booking.facility_id)
    require_facility_entitlement(db, booking.facility_id, operational_write=True)
    if booking.status != "requested":
        raise HTTPException(409, "Only requested appointments can be confirmed")
    code = new_code(db)
    booking.verification_code = hash_booking_code(code)
    booking.verification_code_delivery = encrypt_booking_code(code)
    booking.confirmed_at = datetime.now(timezone.utc)
    booking.status = "confirmed"
    record_audit_event(db, user, "booking.confirmed", "booking", booking.id)
    db.commit()
    db.refresh(booking)
    return managed_booking_data(db, booking)


@router.post("/bookings/{booking_id}/reject", response_model=AdminBookingRead)
def reject_managed_booking(
    booking_id: int,
    payload: BookingDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user)
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if booking is None:
        raise HTTPException(404, "Appointment not found")
    require_staff_facility_access(user, booking.facility_id)
    require_facility_entitlement(db, booking.facility_id, operational_write=True)
    if booking.status != "requested":
        raise HTTPException(409, "Only requested appointments can be rejected")
    booking.status = "rejected"
    booking.rejection_reason = payload.reason
    booking.verification_code = None
    booking.verification_code_delivery = None
    record_audit_event(db, user, "booking.rejected", "booking", booking.id)
    db.commit()
    db.refresh(booking)
    return managed_booking_data(db, booking)


@router.post("/bookings/{booking_id}/complete", response_model=AdminBookingRead)
def complete_managed_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user)
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if booking is None:
        raise HTTPException(404, "Appointment not found")
    require_staff_facility_access(user, booking.facility_id)
    require_facility_entitlement(db, booking.facility_id, operational_write=True)
    if booking.status != "checked_in":
        raise HTTPException(409, "Only checked-in appointments can be completed")
    booking.status = "completed"
    booking.completed_at = datetime.now(timezone.utc)
    record_audit_event(db, user, "booking.completed", "booking", booking.id)
    db.commit()
    db.refresh(booking)
    return managed_booking_data(db, booking)


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingRead)
def cancel_managed_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_staff_facility_access(user)
    booking = db.query(Booking).filter(Booking.id == booking_id).with_for_update().first()
    if booking is None:
        raise HTTPException(404, "Booking not found")
    require_staff_facility_access(user, booking.facility_id)
    require_facility_entitlement(db, booking.facility_id, operational_write=True)
    appointment_at = booking.appointment_at
    if appointment_at.tzinfo is None:
        appointment_at = appointment_at.replace(tzinfo=timezone.utc)
    if appointment_at <= datetime.now(timezone.utc):
        raise HTTPException(409, "Past appointments cannot be cancelled")
    if booking.status not in {"requested", "confirmed"}:
        raise HTTPException(409, "This appointment can no longer be cancelled")
    if booking.payment_status == "paid":
        raise HTTPException(409, "Paid appointments require a refund or credit decision before cancellation")
    booking.status = "cancelled"
    booking.verification_code = None
    booking.verification_code_delivery = None
    record_audit_event(db, user, "booking.cancelled", "booking", booking.id)
    db.commit()
    db.refresh(booking)
    facility = db.get(Facility, booking.facility_id)
    service = db.get(Service, booking.service_id)
    collector = (
        db.get(User, booking.payment_collected_by_user_id)
        if booking.payment_collected_by_user_id is not None
        else None
    )
    return {
        "id": booking.id,
        "facility_id": booking.facility_id,
        "service_id": booking.service_id,
        "appointment_at": booking.appointment_at,
        "payment_method": booking.payment_method,
        "payment_status": booking.payment_status,
        "payment_due_paise": booking.payment_due_paise,
        "payment_amount_paise": booking.payment_amount_paise,
        "payment_currency": booking.payment_currency,
        "payment_collected_at": booking.payment_collected_at,
        "payment_collected_by_user_id": booking.payment_collected_by_user_id,
        "payment_collector_name": collector.name if collector else None,
        "payment_reference": booking.payment_reference,
        "status": booking.status,
        "rejection_reason": booking.rejection_reason,
        "patient_name": booking.patient_name,
        "patient_email_masked": mask_email(booking.patient_email),
        "facility_name": facility.name,
        "service_name": service.name,
        "provider_name": service.provider_name,
    }


@router.get("/users", response_model=list[AdminUserRead])
def list_managed_users(
    include_inactive: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    query = db.query(User, Facility.name).outerjoin(Facility, User.facility_id == Facility.id)
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    rows = query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit).all()
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
    account = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )
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
    if next_role == "facility_staff" and next_facility_id is not None and account.is_active:
        facility = db.get(Facility, next_facility_id)
        if facility is None or not facility.is_active:
            raise HTTPException(422, "The assigned facility must exist and be active")
    elif next_role == "patient":
        next_facility_id = None

    changed = False
    if account.facility_id is not None and account.facility_id != next_facility_id:
        previous_facility = db.get(Facility, account.facility_id)
        if previous_facility is not None and previous_facility.owner_user_id == account.id:
            previous_facility.owner_user_id = None
            previous_subscription = (
                db.query(FacilitySubscription)
                .filter(FacilitySubscription.facility_id == previous_facility.id)
                .with_for_update()
                .first()
            )
            if (
                previous_subscription is not None
                and previous_subscription.billing_contact_user_id == account.id
            ):
                previous_subscription.billing_contact_user_id = None
            record_audit_event(
                db,
                user,
                "facility.billing_owner_removed",
                "facility",
                previous_facility.id,
            )
            changed = True
    for field, value in changes.items():
        if field == "facility_id":
            continue
        if getattr(account, field) != value:
            setattr(account, field, value)
            changed = True
    if account.facility_id != next_facility_id:
        account.facility_id = next_facility_id
        changed = True
    if next_role == "facility_staff" and next_facility_id is not None:
        new_facility = db.get(Facility, next_facility_id)
        if new_facility is not None and new_facility.owner_user_id is None:
            new_facility.owner_user_id = account.id
            new_subscription = (
                db.query(FacilitySubscription)
                .filter(FacilitySubscription.facility_id == new_facility.id)
                .with_for_update()
                .first()
            )
            if new_subscription is not None:
                new_subscription.billing_contact_user_id = account.id
            record_audit_event(
                db,
                user,
                "facility.billing_owner_assigned",
                "facility",
                new_facility.id,
            )
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


@router.get("/subscription-plans", response_model=list[SubscriptionPlanRead])
def list_subscription_plans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    return db.query(SubscriptionPlan).order_by(
        SubscriptionPlan.billing_interval, SubscriptionPlan.id
    ).all()


@router.post(
    "/subscription-plans",
    response_model=SubscriptionPlanRead,
    status_code=201,
)
def create_subscription_plan(
    payload: SubscriptionPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    plan = SubscriptionPlan(**payload.model_dump())
    db.add(plan)
    try:
        db.flush()
        record_audit_event(db, user, "subscription_plan.created", "subscription_plan", plan.id)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "A subscription plan with this name already exists") from error
    db.refresh(plan)
    return plan


@router.patch(
    "/subscription-plans/{plan_id}",
    response_model=SubscriptionPlanRead,
)
def update_subscription_plan(
    plan_id: int,
    payload: SubscriptionPlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Subscription plan not found")
    changes = payload.model_dump(exclude_unset=True)
    active = changes.get("is_active", plan.is_active)
    price = changes.get("price_paise", plan.price_paise)
    if active and (price is None or price <= 0):
        raise HTTPException(422, "Set a positive price before activating this plan")
    for field, value in changes.items():
        setattr(plan, field, value)
    try:
        record_audit_event(db, user, "subscription_plan.updated", "subscription_plan", plan.id)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "A subscription plan with this name already exists") from error
    db.refresh(plan)
    return plan


@router.get("/subscriptions", response_model=list[PlatformSubscriptionRead])
def list_facility_subscriptions(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    rows = (
        db.query(FacilitySubscription, Facility, SubscriptionPlan)
        .join(Facility, FacilitySubscription.facility_id == Facility.id)
        .outerjoin(SubscriptionPlan, FacilitySubscription.plan_id == SubscriptionPlan.id)
        .order_by(Facility.name, FacilitySubscription.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    now = datetime.now(timezone.utc)
    for subscription, _, _ in rows:
        refresh_subscription_state(db, subscription, now)
    if rows:
        db.commit()
    return [
        {
            "id": subscription.id,
            "facility_id": facility.id,
            "facility_name": facility.name,
            "facility_active": facility.is_active,
            "status": effective_subscription_status(subscription, now),
            "plan_name": subscription.plan_name_snapshot or (plan.name if plan else None),
            "billing_interval": subscription.billing_interval_snapshot
            or (plan.billing_interval if plan else None),
            "price_paise": subscription.price_paise_snapshot
            if subscription.price_paise_snapshot is not None
            else (plan.price_paise if plan else None),
            "currency": subscription.currency_snapshot,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "grace_period_end": subscription.grace_period_end,
            "owner_user_id": facility.owner_user_id,
        }
        for subscription, facility, plan in rows
    ]


@router.get(
    "/subscription-payments",
    response_model=list[AdminSubscriptionPaymentRead],
)
def list_subscription_payments(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    rows = (
        db.query(SubscriptionPayment, Facility.name)
        .join(Facility, SubscriptionPayment.facility_id == Facility.id)
        .order_by(SubscriptionPayment.created_at.desc(), SubscriptionPayment.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            **{
                field: getattr(payment, field)
                for field in AdminSubscriptionPaymentRead.model_fields
                if field not in {"facility_id", "facility_name"}
            },
            "facility_id": payment.facility_id,
            "facility_name": facility_name,
        }
        for payment, facility_name in rows
    ]


@router.post(
    "/subscriptions/{subscription_id}/extend",
    response_model=PlatformSubscriptionRead,
)
def extend_facility_subscription(
    subscription_id: int,
    payload: AdminSubscriptionExtension,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    subscription = (
        db.query(FacilitySubscription)
        .filter(FacilitySubscription.id == subscription_id)
        .with_for_update()
        .first()
    )
    if subscription is None:
        raise HTTPException(404, "Facility subscription not found")
    facility = db.get(Facility, subscription.facility_id)
    if facility is None:
        raise HTTPException(409, "The facility for this subscription no longer exists")
    now = datetime.now(timezone.utc)
    start = max(
        subscription.current_period_end.replace(tzinfo=timezone.utc)
        if subscription.current_period_end.tzinfo is None
        else subscription.current_period_end.astimezone(timezone.utc),
        now,
    ) if subscription.current_period_end else now
    subscription.current_period_start = start
    subscription.current_period_end = start + timedelta(days=payload.days)
    subscription.grace_period_end = subscription.current_period_end + timedelta(days=7)
    subscription.status = "active"
    subscription.cancel_at_period_end = False
    record_audit_event(
        db,
        user,
        "subscription.admin_extended",
        "facility_subscription",
        subscription.id,
        details=f"Extended by {payload.days} days. Reason: {payload.reason}",
    )
    db.commit()
    db.refresh(subscription)
    plan = db.get(SubscriptionPlan, subscription.plan_id) if subscription.plan_id else None
    return {
        "id": subscription.id,
        "facility_id": facility.id,
        "facility_name": facility.name,
        "facility_active": facility.is_active,
        "status": effective_subscription_status(subscription),
        "plan_name": subscription.plan_name_snapshot or (plan.name if plan else None),
        "billing_interval": subscription.billing_interval_snapshot
        or (plan.billing_interval if plan else None),
        "price_paise": subscription.price_paise_snapshot
        if subscription.price_paise_snapshot is not None
        else (plan.price_paise if plan else None),
        "currency": subscription.currency_snapshot,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "grace_period_end": subscription.grace_period_end,
        "owner_user_id": facility.owner_user_id,
    }


@router.get("/audit-events", response_model=list[AuditEventRead])
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    return (
        db.query(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get(
    "/payment-webhook-events",
    response_model=list[PaymentWebhookEventRead],
)
def list_payment_webhook_events(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_platform_admin(user)
    return (
        db.query(PaymentWebhookEvent)
        .order_by(PaymentWebhookEvent.received_at.desc(), PaymentWebhookEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
