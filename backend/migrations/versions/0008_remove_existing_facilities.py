"""Remove existing facilities and their linked operational history as requested.

Revision ID: 0008_remove_existing_facilities
Revises: 0007_facility_profile

This migration is intentionally irreversible. Facility-staff accounts are retained
and unassigned; facility data, bookings, documents, payment records, and related
audit history are permanently removed.
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_remove_existing_facilities"
down_revision = "0007_facility_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    facility_ids = sa.select(sa.column("id")).select_from(sa.table("facilities"))
    service_ids = (
        sa.select(sa.column("id"))
        .select_from(sa.table("services"))
        .where(sa.column("facility_id").in_(facility_ids))
    )
    booking_ids = (
        sa.select(sa.column("id"))
        .select_from(sa.table("bookings"))
        .where(sa.column("facility_id").in_(facility_ids))
    )
    document_ids = (
        sa.select(sa.column("id"))
        .select_from(sa.table("booking_documents"))
        .where(sa.column("booking_id").in_(booking_ids))
    )

    audit = sa.table(
        "audit_events",
        sa.column("action"),
        sa.column("resource_type"),
        sa.column("resource_id"),
    )
    bind.execute(
        audit.delete().where(
            sa.or_(
                sa.and_(audit.c.resource_type == "facility", audit.c.resource_id.in_(facility_ids)),
                sa.and_(audit.c.resource_type == "service", audit.c.resource_id.in_(service_ids)),
                sa.and_(audit.c.resource_type == "booking", audit.c.resource_id.in_(booking_ids)),
                sa.and_(
                    audit.c.resource_type == "booking_document",
                    audit.c.resource_id.in_(document_ids),
                ),
            )
        )
    )
    bind.execute(
        sa.delete(sa.table("booking_documents")).where(
            sa.column("booking_id").in_(booking_ids)
        )
    )
    bind.execute(sa.delete(sa.table("bookings")).where(sa.column("facility_id").in_(facility_ids)))
    bind.execute(sa.delete(sa.table("services")).where(sa.column("facility_id").in_(facility_ids)))
    bind.execute(
        sa.update(sa.table("users", sa.column("facility_id")))
        .where(sa.column("facility_id").in_(facility_ids))
        .values(facility_id=None)
    )
    bind.execute(sa.delete(sa.table("facilities")))
    bind.execute(
        sa.insert(audit).values(
            action="facility.data_reset",
            resource_type="system",
            resource_id=None,
        )
    )


def downgrade() -> None:
    raise RuntimeError("Facility and booking data removed by this migration cannot be restored.")
