"""Add facility/service images and verified facility reviews.

Revision ID: 0011_facility_media_and_reviews
Revises: 0010_booking_request_lifecycle
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_facility_media_and_reviews"
down_revision = "0010_booking_request_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("facilities", sa.Column("image_content", sa.LargeBinary(), nullable=True))
    op.add_column("facilities", sa.Column("image_media_type", sa.String(length=30), nullable=True))
    op.add_column("services", sa.Column("image_content", sa.LargeBinary(), nullable=True))
    op.add_column("services", sa.Column("image_media_type", sa.String(length=30), nullable=True))
    op.create_table(
        "facility_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            sa.Integer(),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_facility_reviews_rating"),
        sa.UniqueConstraint("booking_id", name="uq_facility_reviews_booking_id"),
    )
    op.create_index("ix_facility_reviews_booking_id", "facility_reviews", ["booking_id"])
    op.create_index("ix_facility_reviews_facility_id", "facility_reviews", ["facility_id"])
    op.create_index(
        "ix_facility_reviews_patient_user_id",
        "facility_reviews",
        ["patient_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_facility_reviews_patient_user_id", table_name="facility_reviews")
    op.drop_index("ix_facility_reviews_facility_id", table_name="facility_reviews")
    op.drop_index("ix_facility_reviews_booking_id", table_name="facility_reviews")
    op.drop_table("facility_reviews")
    op.drop_column("services", "image_media_type")
    op.drop_column("services", "image_content")
    op.drop_column("facilities", "image_media_type")
    op.drop_column("facilities", "image_content")
