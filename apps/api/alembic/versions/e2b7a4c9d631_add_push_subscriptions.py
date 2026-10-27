"""add push subscriptions

Revision ID: e2b7a4c9d631
Revises: d8e1f2a9c6b3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e2b7a4c9d631"
down_revision: Union[str, None] = "d8e1f2a9c6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("p256dh_key", sa.String(length=255), nullable=False),
        sa.Column("auth_key", sa.String(length=255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_push_subscriptions_user_id",
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_push_subscriptions_endpoint_hash",
        "push_subscriptions",
        ["endpoint_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_push_subscriptions_endpoint_hash",
        table_name="push_subscriptions",
    )
    op.drop_index(
        "ix_push_subscriptions_user_id",
        table_name="push_subscriptions",
    )
    op.drop_table("push_subscriptions")