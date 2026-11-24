"""Add canonical doctor slot reservations and facility map coordinates.

Revision ID: 0012_doctor_slots_and_facility_coordinates
Revises: 0011_facility_media_and_reviews
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_doctor_slots_and_facility_coordinates"
down_revision = "0011_facility_media_and_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("facilities", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("facilities", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("services", sa.Column("provider_key", sa.String(length=80), nullable=True))
    op.add_column("bookings", sa.Column("provider_key", sa.String(length=180), nullable=True))
    op.create_index("ix_services_provider_key", "services", ["provider_key"])
    op.create_index("ix_bookings_provider_key", "bookings", ["provider_key"])

    bind = op.get_bind()
    services = sa.Table(
        "services", sa.MetaData(),
        sa.Column("id", sa.Integer), sa.Column("service_type", sa.String(30)),
        sa.Column("provider_key", sa.String(80)),
    )
    for row in bind.execute(sa.select(services.c.id, services.c.service_type, services.c.provider_key)):
        if row.service_type == "doctor" and not row.provider_key:
            bind.execute(
                services.update().where(services.c.id == row.id).values(provider_key=f"legacy-{row.id}")
            )

    bookings = sa.Table(
        "bookings", sa.MetaData(),
        sa.Column("id", sa.Integer), sa.Column("service_id", sa.Integer),
        sa.Column("appointment_at", sa.DateTime(timezone=True)),
        sa.Column("provider_key", sa.String(180)),
    )
    services_lookup = sa.Table(
        "services", sa.MetaData(),
        sa.Column("id", sa.Integer), sa.Column("provider_key", sa.String(80)),
    )
    rows = bind.execute(
        sa.select(bookings.c.id, bookings.c.appointment_at, services_lookup.c.provider_key)
        .select_from(bookings.join(services_lookup, bookings.c.service_id == services_lookup.c.id))
        .where(services_lookup.c.provider_key.is_not(None))
        .order_by(bookings.c.id)
    ).all()
    reserved = set()
    for row in rows:
        key = (row.provider_key, row.appointment_at)
        if key in reserved:
            continue
        reserved.add(key)
        bind.execute(
            bookings.update().where(bookings.c.id == row.id).values(provider_key=row.provider_key)
        )

    op.create_unique_constraint(
        "uq_booking_provider_slot", "bookings", ["provider_key", "appointment_at"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_booking_provider_slot", "bookings", type_="unique")
    op.drop_index("ix_bookings_provider_key", table_name="bookings")
    op.drop_index("ix_services_provider_key", table_name="services")
    op.drop_column("bookings", "provider_key")
    op.drop_column("services", "provider_key")
    op.drop_column("facilities", "longitude")
    op.drop_column("facilities", "latitude")
