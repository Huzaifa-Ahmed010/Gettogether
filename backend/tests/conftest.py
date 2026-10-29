import os
import tempfile
from uuid import uuid4

import pytest

_test_directory = tempfile.TemporaryDirectory(prefix="gettogether-tests-")
_test_database = os.path.join(_test_directory.name, "tests.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_database.replace(os.sep, '/')}"

from app.api.routes.auth import create_access_token
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import AuditEvent, User


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
    monkeypatch.setattr(settings, "development_show_email_otp", True)


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
