import hashlib
import hmac
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings


def run_migrations(database_url: str, monkeypatch) -> None:
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    monkeypatch.setattr(settings, "database_url", database_url)
    command.upgrade(config, "head")


def test_migrations_create_current_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "fresh.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    run_migrations(database_url, monkeypatch)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {"users", "bookings", "email_verifications", "password_resets", "audit_events"} <= set(
        inspector.get_table_names()
    )
    assert "token_version" in {column["name"] for column in inspector.get_columns("users")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0002_password_reset_and_audit"
        )
    engine.dispose()


def test_migrations_adopt_legacy_schema_without_dropping_users(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE facilities (
            id INTEGER PRIMARY KEY,
            name VARCHAR(180) NOT NULL,
            facility_type VARCHAR(30) NOT NULL,
            address TEXT NOT NULL,
            city VARCHAR(100) NOT NULL,
            phone VARCHAR(30) NOT NULL,
            is_active BOOLEAN NOT NULL
        );
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            email VARCHAR(254) NOT NULL UNIQUE,
            password_hash VARCHAR(256) NOT NULL,
            is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE services (
            id INTEGER PRIMARY KEY,
            facility_id INTEGER NOT NULL,
            name VARCHAR(180) NOT NULL,
            category VARCHAR(100) NOT NULL,
            service_type VARCHAR(30) NOT NULL,
            provider_name VARCHAR(180) NOT NULL,
            fee_paise INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL
        );
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY,
            patient_name VARCHAR(180) NOT NULL,
            patient_email VARCHAR(254) NOT NULL,
            facility_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            appointment_at DATETIME NOT NULL,
            payment_method VARCHAR(20) NOT NULL,
            payment_status VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            verification_code VARCHAR(6) NOT NULL,
            verified_at DATETIME,
            created_at DATETIME NOT NULL
        );
        INSERT INTO users (id, name, email, password_hash, is_active, created_at)
        VALUES (7, 'Existing Patient', 'legacy@example.com', 'hash', 1, '2026-01-01 00:00:00');
        INSERT INTO facilities (id, name, facility_type, address, city, phone, is_active)
        VALUES (2, 'Legacy Center', 'hospital', '1 Main St', 'Oldtown', '', 1);
        INSERT INTO services (id, facility_id, name, category, service_type, provider_name, fee_paise, is_active)
        VALUES (3, 2, 'Legacy Visit', 'General', 'doctor', '', 1000, 1);
        INSERT INTO bookings (
            id, patient_name, patient_email, facility_id, service_id, appointment_at,
            payment_method, payment_status, status, verification_code, created_at
        ) VALUES (
            9, 'Existing Patient', 'legacy@example.com', 2, 3, '2027-01-01 09:00:00',
            'physical', 'unpaid', 'booked', '123456', '2026-01-01 00:00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    database_url = f"sqlite:///{database_path.as_posix()}"
    run_migrations(database_url, monkeypatch)
    engine = create_engine(database_url)
    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"role", "email_verified", "facility_id", "token_version"} <= user_columns
    with engine.connect() as migrated:
        user = migrated.execute(
            text("SELECT id, email, role, email_verified, token_version FROM users WHERE id = 7")
        ).one()
        assert user == (7, "legacy@example.com", "patient", False, 0)
        booking_code = migrated.execute(
            text("SELECT verification_code FROM bookings WHERE id = 9")
        ).scalar_one()
        expected_code = hmac.new(
            settings.secret_key.encode(),
            b"123456",
            hashlib.sha256,
        ).hexdigest()
        assert booking_code == expected_code
    engine.dispose()
