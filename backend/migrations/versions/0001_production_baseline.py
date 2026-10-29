"""Create the production schema and adopt pre-migration installations.

Revision ID: 0001_production_baseline
Revises:
"""

import hashlib
import hmac

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.core.config import settings

revision = "0001_production_baseline"
down_revision = None
branch_labels = None
depends_on = None

metadata = sa.MetaData()

facilities = sa.Table(
    "facilities",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String(180), nullable=False),
    sa.Column("facility_type", sa.String(30), nullable=False),
    sa.Column("address", sa.Text, nullable=False),
    sa.Column("city", sa.String(100), nullable=False),
    sa.Column("phone", sa.String(30), nullable=False, server_default=""),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Index("ix_facilities_id", "id"),
    sa.Index("ix_facilities_name", "name"),
    sa.Index("ix_facilities_facility_type", "facility_type"),
    sa.Index("ix_facilities_city", "city"),
)
services = sa.Table(
    "services",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("facility_id", sa.Integer, sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
    sa.Column("name", sa.String(180), nullable=False),
    sa.Column("category", sa.String(100), nullable=False),
    sa.Column("service_type", sa.String(30), nullable=False),
    sa.Column("provider_name", sa.String(180), nullable=False, server_default=""),
    sa.Column("fee_paise", sa.Integer, nullable=False),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Index("ix_services_id", "id"),
    sa.Index("ix_services_facility_id", "facility_id"),
    sa.Index("ix_services_name", "name"),
    sa.Index("ix_services_category", "category"),
)
bookings = sa.Table(
    "bookings",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("patient_name", sa.String(180), nullable=False),
    sa.Column("patient_email", sa.String(254), nullable=False),
    sa.Column("facility_id", sa.Integer, sa.ForeignKey("facilities.id"), nullable=False),
    sa.Column("service_id", sa.Integer, sa.ForeignKey("services.id"), nullable=False),
    sa.Column("appointment_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payment_method", sa.String(20), nullable=False),
    sa.Column("payment_status", sa.String(20), nullable=False, server_default="unpaid"),
    sa.Column("status", sa.String(20), nullable=False, server_default="booked"),
    sa.Column("verification_code", sa.String(64), nullable=False),
    sa.Column("verified_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.UniqueConstraint("verification_code", name="uq_booking_verification_code"),
    sa.Index("ix_bookings_id", "id"),
    sa.Index("ix_bookings_patient_email", "patient_email"),
    sa.Index("ix_bookings_facility_id", "facility_id"),
    sa.Index("ix_bookings_service_id", "service_id"),
    sa.Index("ix_bookings_appointment_at", "appointment_at"),
    sa.Index("ix_bookings_verification_code", "verification_code"),
)
users = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("email", sa.String(254), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(256), nullable=False),
    sa.Column("role", sa.String(30), nullable=False, server_default="patient"),
    sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("facility_id", sa.Integer, sa.ForeignKey("facilities.id")),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Index("ix_users_id", "id"),
    sa.Index("ix_users_email", "email"),
    sa.Index("ix_users_facility_id", "facility_id"),
)
email_verifications = sa.Table(
    "email_verifications",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    sa.Column("code_hash", sa.String(64), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Index("ix_email_verifications_user_id", "user_id"),
)


def upgrade() -> None:
    bind = op.get_bind()
    metadata.create_all(bind=bind)

    inspector = inspect(bind)
    if "users" in inspector.get_table_names():
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        legacy_user_columns = (
            ("role", sa.String(30), False, "patient"),
            ("email_verified", sa.Boolean(), False, "false"),
            ("facility_id", sa.Integer(), True, None),
        )
        additions = []
        for name, column_type, nullable, default in legacy_user_columns:
            if name not in user_columns:
                foreign_key = (
                    sa.ForeignKey("facilities.id", name="fk_users_facility_id_facilities")
                    if name == "facility_id"
                    else None
                )
                additions.append(
                    sa.Column(
                        name,
                        column_type,
                        foreign_key,
                        nullable=nullable,
                        server_default=sa.text(default) if default is not None else None,
                    )
                )
        if bind.dialect.name == "sqlite" and additions:
            with op.batch_alter_table("users", recreate="always") as batch:
                for column in additions:
                    batch.add_column(column)
        else:
            for column in additions:
                op.add_column("users", column)

    if "bookings" in inspector.get_table_names():
        booking_columns = {
            column["name"]: column for column in inspector.get_columns("bookings")
        }
        verification_code = booking_columns.get("verification_code")
        if (
            bind.dialect.name == "postgresql"
            and verification_code is not None
            and getattr(verification_code["type"], "length", None) != 64
        ):
            op.alter_column(
                "bookings",
                "verification_code",
                existing_type=verification_code["type"],
                type_=sa.String(64),
                existing_nullable=False,
            )
        stored_codes = bind.execute(
            sa.select(bookings.c.id, bookings.c.verification_code)
        ).all()
        for booking_id, code in stored_codes:
            if isinstance(code, str) and code.isdigit() and len(code) == 6:
                digest = hmac.new(
                    settings.secret_key.encode(),
                    code.encode(),
                    hashlib.sha256,
                ).hexdigest()
                bind.execute(
                    bookings.update()
                    .where(bookings.c.id == booking_id)
                    .values(verification_code=digest)
                )


def downgrade() -> None:
    raise RuntimeError("The production baseline is irreversible to protect existing application data.")
