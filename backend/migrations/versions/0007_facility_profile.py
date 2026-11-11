"""Add facility public description and IANA timezone.

Revision ID: 0007_facility_profile
Revises: 0006_booking_documents
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_facility_profile"
down_revision = "0006_booking_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "facilities",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "facilities",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Kolkata"),
    )


def downgrade() -> None:
    op.drop_column("facilities", "timezone")
    op.drop_column("facilities", "description")
