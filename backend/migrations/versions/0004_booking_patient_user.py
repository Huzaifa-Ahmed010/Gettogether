"""Associate bookings with their patient account.

Revision ID: 0004_booking_patient_user
Revises: 0003_optional_user_phone
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_booking_patient_user"
down_revision = "0003_optional_user_phone"
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
            sa.Column(
                "patient_user_id",
                sa.Integer(),
                sa.ForeignKey(
                    "users.id",
                    name="fk_bookings_patient_user_id_users",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )
    op.create_index("ix_bookings_patient_user_id", "bookings", ["patient_user_id"])
    op.execute(
        sa.text(
            """
            UPDATE bookings
            SET patient_user_id = (
                SELECT users.id
                FROM users
                WHERE lower(users.email) = lower(bookings.patient_email)
                LIMIT 1
            )
            WHERE patient_user_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_patient_user_id", table_name="bookings")
    with op.batch_alter_table(
        "bookings",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.drop_column("patient_user_id")
