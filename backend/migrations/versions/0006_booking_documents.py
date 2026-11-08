"""Store private appointment documents in the database.

Revision ID: 0006_booking_documents
Revises: 0005_booking_payment_collection
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_booking_documents"
down_revision = "0005_booking_payment_collection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_booking_documents_id", "booking_documents", ["id"])
    op.create_index("ix_booking_documents_booking_id", "booking_documents", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_documents_booking_id", table_name="booking_documents")
    op.drop_index("ix_booking_documents_id", table_name="booking_documents")
    op.drop_table("booking_documents")
