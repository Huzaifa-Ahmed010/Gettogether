from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, EmailVerification, PasswordReset, User


def test_register_login_and_protected_profile():
    email = f"user-{uuid4().hex}@example.com"
    password = "correct horse battery staple"
    user_id = None

    with TestClient(app) as client:
        try:
            registration = client.post(
                "/api/v1/auth/register",
                json={"name": "Test Patient", "email": email.upper(), "password": password},
            )
            assert registration.status_code == 202
            pending = registration.json()
            with SessionLocal() as db:
                pending_user = db.query(User).filter(User.email == email).first()
                assert pending_user is not None
                user_id = pending_user.id
            assert pending["email"] == email
            assert pending["development_otp"]

            assert client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            ).status_code == 403

            verified = client.post(
                "/api/v1/auth/verify-email",
                json={"email": email, "code": "not-a-code"},
            )
            assert verified.status_code == 422
            verified = client.post(
                "/api/v1/auth/verify-email",
                json={"email": email, "code": pending["development_otp"]},
            )
            assert verified.status_code == 200
            account = verified.json()
            user_id = account["user"]["id"]
            assert account["user"]["email"] == email
            assert "password" not in account["user"]
            assert account["token_type"] == "bearer"
            assert account["expires_in"] > 0

            profile = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {account['access_token']}"},
            )
            assert profile.status_code == 200
            assert profile.json()["id"] == user_id

            login = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            assert login.status_code == 200
            assert login.json()["user"]["id"] == user_id

            assert client.get("/api/v1/auth/me").status_code == 401
            assert client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "not the password"},
            ).status_code == 401
            assert client.post(
                "/api/v1/auth/register",
                json={"name": "Duplicate", "email": email, "password": password},
            ).status_code == 409
            assert client.post(
                "/api/v1/auth/register",
                json={"name": "Short Password", "email": f"short-{email}", "password": "short"},
            ).status_code == 422
            assert client.post(
                "/api/v1/auth/register",
                json={"name": "  ", "email": f"name-{email}", "password": password},
            ).status_code == 422
        finally:
            if user_id is not None:
                with SessionLocal() as db:
                    user = db.get(User, user_id)
                    if user is not None:
                        db.query(PasswordReset).filter(
                            PasswordReset.user_id == user.id
                        ).delete()
                        db.query(AuditEvent).filter(
                            AuditEvent.actor_user_id == user.id
                        ).delete()
                        db.query(EmailVerification).filter(
                            EmailVerification.user_id == user.id
                        ).delete()
                        db.delete(user)
                        db.commit()


def test_email_verification_resend_cooldown_and_invalid_attempts():
    email = f"verify-{uuid4().hex}@example.com"
    password = "correct horse battery staple"
    user_id = None
    with TestClient(app) as client:
        try:
            registration = client.post(
                "/api/v1/auth/register",
                json={"name": "Verification Test", "email": email, "password": password},
            )
            assert registration.status_code == 202
            assert client.post(
                "/api/v1/auth/resend-verification",
                json={"email": email},
            ).status_code == 429

            with SessionLocal() as db:
                user = db.query(User).filter(User.email == email).first()
                assert user is not None
                user_id = user.id
                verification = db.query(EmailVerification).filter(
                    EmailVerification.user_id == user.id
                ).first()
                assert verification is not None
                verification.sent_at = verification.sent_at.replace(year=verification.sent_at.year - 1)
                db.commit()

            resend = client.post(
                "/api/v1/auth/resend-verification",
                json={"email": email},
            )
            assert resend.status_code == 200
            assert resend.json()["development_otp"]

            for _ in range(5):
                invalid = client.post(
                    "/api/v1/auth/verify-email",
                    json={"email": email, "code": "000000" if resend.json()["development_otp"] != "000000" else "000001"},
                )
            assert invalid.status_code == 429
            with SessionLocal() as db:
                assert db.query(EmailVerification).filter(
                    EmailVerification.user_id == user_id
                ).first() is None
        finally:
            if user_id is not None:
                with SessionLocal() as db:
                    user = db.get(User, user_id)
                    if user is not None:
                        db.query(PasswordReset).filter(
                            PasswordReset.user_id == user.id
                        ).delete()
                        db.query(AuditEvent).filter(
                            AuditEvent.actor_user_id == user.id
                        ).delete()
                        db.delete(user)
                        db.commit()


def test_profile_rejects_invalid_access_token():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
    assert response.status_code == 401


def test_email_delivery_failure_allows_immediate_retry(monkeypatch):
    import app.api.routes.auth as auth_routes

    email = f"delivery-{uuid4().hex}@example.com"
    user_id = None

    def fail_delivery(_recipient, _code):
        raise OSError("test SMTP failure")

    monkeypatch.setattr(auth_routes, "send_verification_code", fail_delivery)
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "name": "Delivery Test",
                    "email": email,
                    "password": "correct horse battery staple",
                },
            )
            assert response.status_code == 503
            with SessionLocal() as db:
                user = db.query(User).filter(User.email == email).first()
                assert user is not None
                user_id = user.id
                assert db.query(EmailVerification).filter(
                    EmailVerification.user_id == user.id
                ).first() is None
        finally:
            if user_id is not None:
                with SessionLocal() as db:
                    user = db.get(User, user_id)
                    if user:
                        db.query(AuditEvent).filter(
                            AuditEvent.actor_user_id == user.id
                        ).delete()
                        db.delete(user)
                        db.commit()


def test_password_reset_revokes_existing_access_tokens():
    email = f"reset-{uuid4().hex}@example.com"
    old_password = "correct horse battery staple"
    new_password = "a different secure password"
    user_id = None

    with TestClient(app) as client:
        try:
            registration = client.post(
                "/api/v1/auth/register",
                json={"name": "Reset User", "email": email, "password": old_password},
            )
            assert registration.status_code == 202
            verified = client.post(
                "/api/v1/auth/verify-email",
                json={"email": email, "code": registration.json()["development_otp"]},
            )
            assert verified.status_code == 200
            old_token = verified.json()["access_token"]
            with SessionLocal() as db:
                user = db.query(User).filter(User.email == email).first()
                assert user is not None
                user_id = user.id

            requested = client.post(
                "/api/v1/auth/request-password-reset",
                json={"email": email},
            )
            assert requested.status_code == 202
            reset = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "email": email,
                    "code": requested.json()["development_otp"],
                    "new_password": new_password,
                },
            )
            assert reset.status_code == 200
            assert client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {old_token}"},
            ).status_code == 401
            assert client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": old_password},
            ).status_code == 401
            assert client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": new_password},
            ).status_code == 200
            with SessionLocal() as db:
                assert db.query(AuditEvent).filter(
                    AuditEvent.actor_user_id == user_id,
                    AuditEvent.action == "account.password_reset",
                ).count() == 1
        finally:
            if user_id is not None:
                with SessionLocal() as db:
                    db.query(PasswordReset).filter(PasswordReset.user_id == user_id).delete()
                    db.query(EmailVerification).filter(EmailVerification.user_id == user_id).delete()
                    db.query(AuditEvent).filter(AuditEvent.actor_user_id == user_id).delete()
                    user = db.get(User, user_id)
                    if user:
                        db.delete(user)
                    db.commit()


def test_production_settings_reject_insecure_origins_and_database():
    from pydantic import ValidationError

    from app.core.config import Settings

    secure_settings = {
        "environment": "production",
        "secret_key": "a" * 64,
        "database_url": "postgresql+psycopg://user:password@db:5432/gettogether?sslmode=verify-full",
        "cors_origins": "https://gettogether.example",
        "allowed_hosts": "api.gettogether.example",
        "trusted_proxy_ips": "10.0.0.8,10.2.0.0/16",
        "redis_url": "rediss://cache.example:6379/0",
        "smtp_host": "smtp.example",
        "smtp_from_email": "accounts@example.com",
        "development_show_email_otp": False,
    }
    assert Settings(**secure_settings).environment == "production"

    for changes in (
        {"secret_key": "development-only-change-me"},
        {"database_url": "sqlite:///./gettogether.db"},
        {"cors_origins": "http://localhost:5173"},
        {"allowed_hosts": "*"},
        {"allowed_hosts": "localhost"},
        {"trusted_proxy_ips": ""},
        {"trusted_proxy_ips": "*"},
        {"trusted_proxy_ips": "proxy.example"},
        {"trusted_proxy_ips": "0.0.0.0/0"},
        {"trusted_proxy_ips": "10.0.0.0/8"},
        {"secret_key": "replace-with-at-least-64-random-characters"},
        {"secret_key": "a" * 63},
        {"database_url": "mysql://user:pass@db:3306/app?sslmode=require"},
        {"cors_origins": "https://gettogether.example/"},
        {"redis_url": "redis://cache.example:6379/0"},
        {"database_url": "postgresql+psycopg://user:password@db:5432/gettogether"},
        {"smtp_host": ""},
        {"development_show_email_otp": True},
        {"smtp_use_starttls": False},
    ):
        with pytest.raises(ValidationError):
            Settings(**(secure_settings | changes))

    insecure_duplicate_sslmode = secure_settings["database_url"].replace(
        "?sslmode=verify-full",
        "?sslmode=disable&sslmode=verify-full",
    )
    with pytest.raises(ValidationError):
        Settings(**(secure_settings | {"database_url": insecure_duplicate_sslmode}))
