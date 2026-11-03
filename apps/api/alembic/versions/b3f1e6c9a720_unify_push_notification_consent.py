"""unify streak and engagement push notification consent

Revision ID: b3f1e6c9a720
Revises: 7a6820b55323
Create Date: 2026-11-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3f1e6c9a720"
down_revision: Union[str, None] = "7a6820b55323"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Owner-confirmed test environment: enable both categories for all accounts
    # that exist at migration time. Future accounts are not included. New ORM-
    # created preference rows default both fields to False in the model.
    op.execute(
        sa.text(
            """
            UPDATE user_preferences
            SET notifications_enabled = TRUE,
                engagement_notifications_enabled = TRUE
            """
        )
    )


def downgrade() -> None:
    # Do not reverse users' notification choices during downgrade.
    pass
