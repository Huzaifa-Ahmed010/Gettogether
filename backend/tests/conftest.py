import os
import tempfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

_test_directory = tempfile.TemporaryDirectory(prefix="gettogether-tests-")
_test_database = os.path.join(_test_directory.name, "tests.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_database.replace(os.sep, '/')}"

from app.api.routes.auth import create_access_token
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import AuditEvent, FacilitySubscription, User


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _test_directory.cleanup()


def pytest_sessionstart(session):
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def strong_test_secret(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "test-secret-" + "x" * 64)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from_email", "")


@pytest.fixture
def otp_delivery(monkeypatch):
    import app.api.routes.auth as auth_routes

    delivered = {"verification": {}, "password_reset": {}}
    monkeypatch.setattr(
        auth_routes,
        "send_verification_code",
        lambda recipient, code: delivered["verification"].__setitem__(recipient, code),
    )
    monkeypatch.setattr(
        auth_routes,
        "send_password_reset_code",
        lambda recipient, code: delivered["password_reset"].__setitem__(recipient, code),
    )
    return delivered


@pytest.fixture
def platform_admin_headers():
    with SessionLocal() as db:
        admin = User(
            name="Test Platform Admin",
            email=f"admin-{uuid4().hex}@example.com",
            password_hash="test-only-password-hash",
            role="platform_admin",
            email_verified=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        headers = {"Authorization": f"Bearer {create_access_token(admin)}"}
        user_id = admin.id
    yield headers
    with SessionLocal() as db:
        db.query(AuditEvent).filter(AuditEvent.actor_user_id == user_id).delete()
        admin = db.get(User, user_id)
        if admin is not None:
            db.delete(admin)
            db.commit()


@pytest.fixture
def account_factory():
    account_ids: list[int] = []

    def create_account(role: str, *, facility_id: int | None = None):
        with SessionLocal() as db:
            account = User(
                name=f"Test {role}",
                email=f"{role}-{uuid4().hex}@example.com",
                password_hash="test-only-password-hash",
                role=role,
                email_verified=True,
                facility_id=facility_id,
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            account_ids.append(account.id)
            return account.id, {"Authorization": f"Bearer {create_access_token(account)}"}

    yield create_account

    if account_ids:
        with SessionLocal() as db:
            db.query(AuditEvent).filter(AuditEvent.actor_user_id.in_(account_ids)).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id.in_(account_ids)).update(
                {User.facility_id: None},
                synchronize_session=False,
            )
            db.query(User).filter(User.id.in_(account_ids)).delete(synchronize_session=False)
            db.commit()


@pytest.fixture
def grant_facility_entitlement():
    def grant(facility_id: int) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            subscription = (
                db.query(FacilitySubscription)
                .filter(FacilitySubscription.facility_id == facility_id)
                .first()
            )
            if subscription is None:
                subscription = FacilitySubscription(facility_id=facility_id)
                db.add(subscription)
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=30)
            subscription.grace_period_end = now + timedelta(days=37)
            db.commit()

    return grant
