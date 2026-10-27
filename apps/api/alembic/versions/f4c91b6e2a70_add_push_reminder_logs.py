from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f4c91b6e2a70"
down_revision = "e2b7a4c9d631"  # Replace if `alembic heads` showed another revision.
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_reminder_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("reminder_date", sa.Date(), nullable=False),
        sa.Column("reminder_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "reminder_date",
            "reminder_type",
            name="uq_push_reminder_user_date_type",
        ),
    )

    op.create_index(
        "ix_push_reminder_logs_status",
        "push_reminder_logs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_push_reminder_logs_status",
        table_name="push_reminder_logs",
    )
    op.drop_table("push_reminder_logs")