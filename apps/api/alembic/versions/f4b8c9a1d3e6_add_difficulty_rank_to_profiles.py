"""add difficulty_rank to profiles

Revision ID: f4b8c9a1d3e6
Revises: a3c81f0d5e72
Create Date: 2026-09-22 00:00:00.000000

Adds the one new column the adaptive-difficulty feature needs
(app/mysteries/progression.py): a computed 1-5 skill level used only to pick
the next encounter's difficulty for a player. It is NOT backfilled from
existing solve counts or XP — every profile starts at the same rank 1 that a
new player gets, and climbs the normal way (rank_after_solve) from here.
Backfilling from historical stats would be assigning skill nobody has
actually demonstrated under this system, which is exactly the kind of
fabricated progression this feature is meant to avoid.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f4b8c9a1d3e6'
down_revision: Union[str, None] = 'a3c81f0d5e72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('profiles', sa.Column('difficulty_rank', sa.Integer(), nullable=False, server_default='1'))
    op.alter_column('profiles', 'difficulty_rank', server_default=None)  # ORM supplies the default from here on


def downgrade() -> None:
    op.drop_column('profiles', 'difficulty_rank')
