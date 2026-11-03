"""Add an optional phone contact field to user accounts.

Revision ID: 0003_optional_user_phone
Revises: 0002_password_reset_and_audit
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_optional_user_phone"
down_revision = "0002_password_reset_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    user_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "phone" not in user_columns:
        op.add_column("users", sa.Column("phone", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone")
