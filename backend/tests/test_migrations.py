import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings


def run_migrations(database_url: str, monkeypatch, revision: str = "head") -> None:
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    monkeypatch.setattr(settings, "database_url", database_url)
    command.upgrade(config, revision)


def test_migrations_create_current_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "fresh.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    run_migrations(database_url, monkeypatch)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "users",
        "bookings",
        "booking_documents",
        "email_verifications",
        "password_resets",
        "audit_events",
        "subscription_plans",
        "facility_subscriptions",
        "subscription_payments",
        "payment_webhook_events",
        "subscription_notices",
    } <= set(
        inspector.get_table_names()
    )
    assert "token_version" in {column["name"] for column in inspector.get_columns("users")}
    assert "phone" in {column["name"] for column in inspector.get_columns("users")}
    assert "patient_user_id" in {
        column["name"] for column in inspector.get_columns("bookings")
    }
    assert {"description", "timezone"} <= {
        column["name"] for column in inspector.get_columns("facilities")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0010_booking_request_lifecycle"
        )
        assert {
            "payment_due_paise",
            "payment_amount_paise",
            "payment_currency",
            "payment_collected_by_user_id",
            "payment_collected_at",
            "payment_reference",
        } <= {column["name"] for column in inspector.get_columns("bookings")}
        assert {
            "booking_id",
            "uploaded_by_user_id",
            "filename",
            "media_type",
            "size_bytes",
            "sha256",
            "content",
            "uploaded_at",
        } <= {column["name"] for column in inspector.get_columns("booking_documents")}
    engine.dispose()


def test_facility_reset_removes_linked_data_and_retains_unassigned_staff(tmp_path, monkeypatch):
    database_path = tmp_path / "facility-reset.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    run_migrations(database_url, monkeypatch, "0007_facility_profile")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, name, email, password_hash, role, email_verified, "
                "token_version, facility_id, is_active, created_at) "
                "VALUES (11, 'Facility Staff', 'staff@example.com', 'hash', "
                "'facility_staff', 0, 0, 1, 1, '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (id, name, email, password_hash, role, email_verified, "
                "token_version, is_active, created_at) "
                "VALUES (12, 'Patient', 'patient@example.com', 'hash', "
                "'patient', 0, 0, 1, '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO facilities (id, name, facility_type, address, city, phone, "
                "description, timezone, is_active) "
                "VALUES (1, 'Reset Center', 'hospital', '1 Main Street', 'Town', '', "
                "'', 'Asia/Kolkata', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO services (id, facility_id, name, category, service_type, "
                "provider_name, fee_paise, is_active) "
                "VALUES (21, 1, 'Consultation', 'Primary', 'doctor', '', 1000, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO bookings (id, patient_user_id, patient_name, patient_email, "
                "facility_id, service_id, appointment_at, payment_method, payment_status, "
                "payment_due_paise, payment_currency, status, verification_code, created_at) "
                "VALUES (31, 12, 'Patient', 'patient@example.com', 1, 21, "
                "'2027-01-01 09:00:00', 'physical', 'unpaid', 1000, 'INR', 'booked', "
                "'hashed-code', '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO booking_documents (id, booking_id, uploaded_by_user_id, filename, "
                "media_type, size_bytes, sha256, content, uploaded_at) "
                "VALUES (41, 31, 12, 'report.pdf', 'application/pdf', 4, 'hash', "
                "X'25504446', '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_events (actor_user_id, action, resource_type, resource_id, created_at) "
                "VALUES (11, 'facility.updated', 'facility', 1, '2026-01-01 00:00:00'), "
                "(11, 'service.updated', 'service', 21, '2026-01-01 00:00:00'), "
                "(12, 'booking.created', 'booking', 31, '2026-01-01 00:00:00'), "
                "(12, 'booking.document_downloaded', 'booking_document', 41, '2026-01-01 00:00:00')"
            )
        )
    run_migrations(database_url, monkeypatch)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, role, facility_id FROM users WHERE id = 11")
        ).one() == (11, "facility_staff", None)
        assert connection.execute(
            text("SELECT id, email FROM users ORDER BY id")
        ).all() == [(11, "staff@example.com"), (12, "patient@example.com")]
        for table in ("facilities", "services", "bookings", "booking_documents"):
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM audit_events WHERE resource_type != 'system'")
        ).scalar_one() == 0
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
    assert {"role", "email_verified", "facility_id", "token_version", "phone"} <= user_columns
    assert "patient_user_id" in {
        column["name"] for column in inspector.get_columns("bookings")
    }
    assert {
        "payment_due_paise",
        "payment_amount_paise",
        "payment_currency",
        "payment_collected_by_user_id",
        "payment_collected_at",
        "payment_reference",
    } <= {column["name"] for column in inspector.get_columns("bookings")}
    assert "booking_documents" in inspector.get_table_names()
    with engine.connect() as migrated:
        user = migrated.execute(
            text("SELECT id, email, role, email_verified, token_version, phone FROM users WHERE id = 7")
        ).one()
        assert user == (7, "legacy@example.com", "patient", False, 0, None)
        assert migrated.execute(text("SELECT COUNT(*) FROM facilities")).scalar_one() == 0
        assert migrated.execute(text("SELECT COUNT(*) FROM services")).scalar_one() == 0
        assert migrated.execute(text("SELECT COUNT(*) FROM bookings")).scalar_one() == 0
        assert migrated.execute(
            text(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE action = 'facility.data_reset' AND resource_type = 'system'"
            )
        ).scalar_one() == 1
    engine.dispose()
