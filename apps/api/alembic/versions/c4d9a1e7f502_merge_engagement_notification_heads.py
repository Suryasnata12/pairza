"""merge engagement notification migration heads

Revision ID: c4d9a1e7f502
Revises: da162c4f8183, b3f1e6c9a720
Create Date: 2026-11-03
"""

from typing import Sequence, Union


revision: str = "c4d9a1e7f502"

down_revision: Union[str, Sequence[str], None] = (
    "da162c4f8183",
    "b3f1e6c9a720",
)

branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
