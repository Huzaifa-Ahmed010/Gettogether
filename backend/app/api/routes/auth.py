import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.audit import record_audit_event
from app.core.email import send_password_reset_code, send_verification_code
from app.db.session import get_db
from app.models import EmailVerification, PasswordReset, User
from app.schemas.auth import (
    EmailCodeRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetCompleteRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    TokenResponse,
    UserRead,
    VerificationPendingResponse,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-account-password")
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_email_code(code: str) -> str:
    return hmac.new(settings.secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def normalize_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def issue_email_code(user: User, db: Session) -> str:
    now = utc_now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    verification = db.query(EmailVerification).filter(EmailVerification.user_id == user.id).first()
    if verification is None:
        verification = EmailVerification(user_id=user.id, code_hash=hash_email_code(code), expires_at=now, sent_at=now)
        db.add(verification)
    verification.code_hash = hash_email_code(code)
    verification.expires_at = now + timedelta(minutes=settings.email_otp_expire_minutes)
    verification.sent_at = now
    verification.attempts = 0
    db.commit()

    try:
        send_verification_code(user.email, code)
    except (OSError, smtplib.SMTPException, RuntimeError) as error:
        db.delete(verification)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't send the verification email. Please try again shortly.",
        ) from error
    if (
        settings.environment.lower() != "production"
        and settings.development_show_email_otp
        and not settings.smtp_host
    ):
        return code
    return ""


def issue_password_reset_code(user: User, db: Session) -> str:
    now = utc_now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    reset = db.query(PasswordReset).filter(PasswordReset.user_id == user.id).first()
    if reset is None:
        reset = PasswordReset(
            user_id=user.id,
            code_hash=hash_email_code(code),
            expires_at=now,
            sent_at=now,
        )
        db.add(reset)
    reset.code_hash = hash_email_code(code)
    reset.expires_at = now + timedelta(minutes=settings.password_reset_expire_minutes)
    reset.sent_at = now
    reset.attempts = 0
    db.commit()

    try:
        send_password_reset_code(user.email, code)
    except (OSError, smtplib.SMTPException, RuntimeError):
        logger.exception("Password reset email delivery failed")
        db.delete(reset)
        db.commit()
        return ""
    if (
        settings.environment.lower() != "production"
        and settings.development_show_email_otp
        and not settings.smtp_host
    ):
        return code
    return ""


def create_access_token(user: User) -> str:
    now = utc_now()
    return jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.token_version,
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        },
        settings.secret_key,
        algorithm="HS256",
    )


def token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid access token is required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized

    user = db.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or not user.email_verified
        or payload.get("ver", 0) != user.token_version
    ):
        raise unauthorized
    return user


@router.post(
    "/register",
    response_model=VerificationPendingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(name=payload.name.strip(), email=email, password_hash=password_hash.hash(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    db.refresh(user)
    record_audit_event(db, user, "account.registered", "user", user.id)
    development_otp = issue_email_code(user, db)
    return VerificationPendingResponse(
        message="Enter the verification code sent to your email address.",
        email=email,
        development_otp=development_otp or None,
    )


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(payload: EmailCodeRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    verification = (
        db.query(EmailVerification)
        .filter(EmailVerification.user_id == user.id)
        .with_for_update()
        .first()
        if user is not None
        else None
    )
    if user is None or verification is None or user.email_verified:
        raise HTTPException(status_code=400, detail="The verification code is invalid or expired")

    now = utc_now()
    if normalize_datetime(verification.expires_at) <= now:
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=400, detail="The verification code is invalid or expired")
    if verification.attempts >= settings.email_otp_max_attempts:
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new verification code.")
    if not hmac.compare_digest(verification.code_hash, hash_email_code(payload.code)):
        verification.attempts += 1
        attempts_exhausted = verification.attempts >= settings.email_otp_max_attempts
        if attempts_exhausted:
            db.delete(verification)
        db.commit()
        if attempts_exhausted:
            raise HTTPException(status_code=429, detail="Too many attempts. Request a new verification code.")
        raise HTTPException(status_code=400, detail="The verification code is invalid or expired")

    user.email_verified = True
    db.delete(verification)
    record_audit_event(db, user, "account.email_verified", "user", user.id)
    db.commit()
    db.refresh(user)
    return token_response(user)


@router.post("/resend-verification", response_model=ResendVerificationResponse)
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    generic_message = "If this address has an account that needs verification, a code will be sent."
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if user is None or user.email_verified:
        return ResendVerificationResponse(message=generic_message)

    previous = db.query(EmailVerification).filter(EmailVerification.user_id == user.id).first()
    if previous is not None:
        elapsed = (utc_now() - normalize_datetime(previous.sent_at)).total_seconds()
        if elapsed < settings.email_otp_resend_seconds:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {settings.email_otp_resend_seconds - int(elapsed)} seconds before requesting another code.",
            )
    development_otp = issue_email_code(user, db)
    return ResendVerificationResponse(
        message=generic_message,
        development_otp=development_otp or None,
    )


@router.post("/request-password-reset", response_model=PasswordResetResponse, status_code=202)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    generic_message = "If the address belongs to an active verified account, a reset code will be sent."
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(
        User.email == email,
        User.email_verified.is_(True),
        User.is_active.is_(True),
    ).first()
    if user is None:
        return PasswordResetResponse(message=generic_message)

    previous = db.query(PasswordReset).filter(PasswordReset.user_id == user.id).first()
    if previous is not None:
        elapsed = (utc_now() - normalize_datetime(previous.sent_at)).total_seconds()
        if elapsed < settings.email_otp_resend_seconds:
            return PasswordResetResponse(message=generic_message)

    development_otp = issue_password_reset_code(user, db)
    return PasswordResetResponse(
        message=generic_message,
        development_otp=development_otp or None,
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: PasswordResetCompleteRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    reset = (
        db.query(PasswordReset)
        .filter(PasswordReset.user_id == user.id)
        .with_for_update()
        .first()
        if user is not None
        else None
    )
    invalid = HTTPException(status_code=400, detail="The reset code is invalid or expired")
    if user is None or reset is None:
        raise invalid
    if normalize_datetime(reset.expires_at) <= utc_now():
        db.delete(reset)
        db.commit()
        raise invalid
    if reset.attempts >= settings.email_otp_max_attempts:
        db.delete(reset)
        db.commit()
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new reset code.")
    if not hmac.compare_digest(reset.code_hash, hash_email_code(payload.code)):
        reset.attempts += 1
        attempts_exhausted = reset.attempts >= settings.email_otp_max_attempts
        if attempts_exhausted:
            db.delete(reset)
        db.commit()
        if attempts_exhausted:
            raise HTTPException(status_code=429, detail="Too many attempts. Request a new reset code.")
        raise invalid

    user.password_hash = password_hash.hash(payload.new_password)
    user.token_version += 1
    db.delete(reset)
    record_audit_event(db, user, "account.password_reset", "user", user.id)
    db.commit()
    return MessageResponse(message="Your password was updated. Sign in with your new password.")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        password_hash.verify(payload.password, DUMMY_PASSWORD_HASH)
    if user is None or not password_hash.verify(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Enter your email verification code to continue.",
        )
    record_audit_event(db, user, "account.login", "user", user.id)
    db.commit()
    return token_response(user)


@router.get("/me", response_model=UserRead)
def current_account(user: User = Depends(get_current_user)):
    return user
