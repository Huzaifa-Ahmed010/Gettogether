"""Add facility-owned subscription plans, entitlements, and payment records.

Revision ID: 0009_facility_subscriptions
Revises: 0008_remove_existing_facilities
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_facility_subscriptions"
down_revision = "0008_remove_existing_facilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("details", sa.Text(), nullable=True))
    with op.batch_alter_table(
        "facilities",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_facilities_owner_user_id_users",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_facilities_owner_user_id", "facilities", ["owner_user_id"])

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("billing_interval", sa.String(length=20), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "billing_interval IN ('monthly', 'quarterly', 'yearly')",
            name="ck_subscription_plans_billing_interval",
        ),
        sa.CheckConstraint("price_paise IS NULL OR price_paise >= 0", name="ck_subscription_plans_price"),
    )
    op.create_index("ix_subscription_plans_billing_interval", "subscription_plans", ["billing_interval"])

    op.create_table(
        "facility_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "facility_id",
            sa.Integer(),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("subscription_plans.id", ondelete="SET NULL")),
        sa.Column("billing_contact_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_payment"),
        sa.Column("plan_name_snapshot", sa.String(length=100)),
        sa.Column("billing_interval_snapshot", sa.String(length=20)),
        sa.Column("price_paise_snapshot", sa.Integer()),
        sa.Column("currency_snapshot", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("grace_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("facility_id", name="uq_facility_subscription_facility"),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'active', 'grace_period', 'expired', 'cancelled')",
            name="ck_facility_subscriptions_status",
        ),
        sa.CheckConstraint(
            "price_paise_snapshot IS NULL OR price_paise_snapshot >= 0",
            name="ck_facility_subscriptions_price_snapshot",
        ),
    )
    op.create_index("ix_facility_subscriptions_facility_id", "facility_subscriptions", ["facility_id"])
    op.create_index("ix_facility_subscriptions_status", "facility_subscriptions", ["status"])

    op.create_table(
        "subscription_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "facility_id",
            sa.Integer(),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("facility_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("subscription_plans.id", ondelete="SET NULL")),
        sa.Column("gateway", sa.String(length=30), nullable=False, server_default="razorpay"),
        sa.Column("gateway_order_id", sa.String(length=120), unique=True),
        sa.Column("gateway_payment_id", sa.String(length=120), unique=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("plan_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("billing_interval_snapshot", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="created"),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.String(length=300)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_paise > 0", name="ck_subscription_payments_amount"),
        sa.CheckConstraint(
            "status IN ('created', 'pending', 'paid', 'failed', 'refunded', 'partially_refunded')",
            name="ck_subscription_payments_status",
        ),
    )
    op.create_index("ix_subscription_payments_facility_id", "subscription_payments", ["facility_id"])
    op.create_index("ix_subscription_payments_subscription_id", "subscription_payments", ["subscription_id"])
    op.create_index("ix_subscription_payments_status", "subscription_payments", ["status"])

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gateway_event_id", sa.String(length=120), nullable=False, unique=True),
        sa.Column("gateway", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "processing_status IN ('received', 'processed', 'ignored')",
            name="ck_payment_webhook_events_processing_status",
        ),
    )
    op.create_table(
        "subscription_notices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "facility_id",
            sa.Integer(),
            sa.ForeignKey("facilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("facility_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "subscription_id",
            "event_key",
            name="uq_subscription_notice_event",
        ),
    )
    op.create_index("ix_subscription_notices_facility_id", "subscription_notices", ["facility_id"])
    op.create_index("ix_subscription_notices_subscription_id", "subscription_notices", ["subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_subscription_notices_subscription_id", table_name="subscription_notices")
    op.drop_index("ix_subscription_notices_facility_id", table_name="subscription_notices")
    op.drop_table("subscription_notices")
    op.drop_table("payment_webhook_events")
    op.drop_index("ix_subscription_payments_status", table_name="subscription_payments")
    op.drop_index("ix_subscription_payments_subscription_id", table_name="subscription_payments")
    op.drop_index("ix_subscription_payments_facility_id", table_name="subscription_payments")
    op.drop_table("subscription_payments")
    op.drop_index("ix_facility_subscriptions_status", table_name="facility_subscriptions")
    op.drop_index("ix_facility_subscriptions_facility_id", table_name="facility_subscriptions")
    op.drop_table("facility_subscriptions")
    op.drop_index("ix_subscription_plans_billing_interval", table_name="subscription_plans")
    op.drop_table("subscription_plans")
    op.drop_index("ix_facilities_owner_user_id", table_name="facilities")
    with op.batch_alter_table(
        "facilities",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch_op:
        batch_op.drop_constraint("fk_facilities_owner_user_id_users", type_="foreignkey")
        batch_op.drop_column("owner_user_id")
    op.drop_column("audit_events", "details")
