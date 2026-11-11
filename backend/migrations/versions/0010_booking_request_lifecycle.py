"""Move booking requests to the confirmed-only check-in-code lifecycle.

Revision ID: 0010_booking_request_lifecycle
Revises: 0009_facility_subscriptions
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_booking_request_lifecycle"
down_revision = "0009_facility_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE bookings SET status = 'requested' WHERE status = 'booked'")
    op.execute("UPDATE bookings SET status = 'checked_in' WHERE status = 'verified'")
    op.execute(
        "UPDATE bookings SET verification_code = NULL "
        "WHERE status != 'confirmed'"
    )
    with op.batch_alter_table(
        "bookings",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.alter_column(
            "verification_code",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        batch_op.add_column(sa.Column("verification_code_delivery", sa.String(length=256)))
        batch_op.add_column(sa.Column("confirmed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("rejection_reason", sa.String(length=500)))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    raise RuntimeError("The booking request lifecycle migration is intentionally irreversible.")
