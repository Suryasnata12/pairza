"""resync mystery status with is_published

Revision ID: a3c81f0d5e72
Revises: 5267531369ca
Create Date: 2026-09-19 00:00:00.000000

Data-only migration (no schema change). Repairs rows left inconsistent by two
bugs fixed in the same commit:

  1. scripts/seed.py created mysteries with is_published=true but never set
     `status`, so they sat at the DRAFT default. The earlier backfill in
     5267531369ca ran BEFORE the seed on a fresh database, so it never saw them.
  2. admin publish / unpublish / PATCH changed is_published without touching
     `status`.

`is_published` is the gate matchmaking actually reads, so it is treated as the
source of truth and `status` is brought in line with it.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a3c81f0d5e72'
down_revision: Union[str, None] = '5267531369ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Live in rotation -> must read as PUBLISHED.
    op.execute("UPDATE mysteries SET status = 'PUBLISHED' WHERE is_published = true AND status <> 'PUBLISHED'")
    # Marked PUBLISHED but pulled from rotation (admin unpublished it under the old code) -> DISABLED.
    op.execute("UPDATE mysteries SET status = 'DISABLED' WHERE is_published = false AND status = 'PUBLISHED'")


def downgrade() -> None:
    # Intentionally a no-op: the previous values were inconsistent by definition,
    # and there is nothing meaningful to restore them to.
    pass
