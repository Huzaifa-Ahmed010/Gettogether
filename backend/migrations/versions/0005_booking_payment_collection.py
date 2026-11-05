"""Record pay-at-facility collections before check-in.

Revision ID: 0005_booking_payment_collection
Revises: 0004_booking_patient_user
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_booking_payment_collection"
down_revision = "0004_booking_patient_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table(
        "bookings",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.add_column(
            sa.Column("payment_due_paise", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("payment_amount_paise", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("payment_currency", sa.String(length=3), nullable=False, server_default="INR")
        )
        batch_op.add_column(
            sa.Column("payment_collected_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_bookings_payment_collected_by_user_id_users",
            "users",
            ["payment_collected_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.add_column(
            sa.Column("payment_collected_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("payment_reference", sa.String(length=120), nullable=True))

    op.create_index(
        "ix_bookings_payment_collected_by_user_id",
        "bookings",
        ["payment_collected_by_user_id"],
    )
    op.execute(
        sa.text(
            """
            UPDATE bookings
            SET payment_due_paise = (
                SELECT services.fee_paise
                FROM services
                WHERE services.id = bookings.service_id
            )
            WHERE EXISTS (
                SELECT 1 FROM services WHERE services.id = bookings.service_id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE bookings
            SET payment_status = 'not_required'
            WHERE payment_due_paise = 0 AND payment_status = 'unpaid'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_payment_collected_by_user_id", table_name="bookings")
    with op.batch_alter_table(
        "bookings",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.drop_column("payment_reference")
        batch_op.drop_column("payment_collected_at")
        batch_op.drop_constraint(
            "fk_bookings_payment_collected_by_user_id_users", type_="foreignkey"
        )
        batch_op.drop_column("payment_collected_by_user_id")
        batch_op.drop_column("payment_currency")
        batch_op.drop_column("payment_amount_paise")
        batch_op.drop_column("payment_due_paise")
