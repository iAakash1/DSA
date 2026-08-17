"""A chosen ICPC target rating, distinct from an assumed one

Readiness measures rating depth against a target. Without somewhere to record
the user's own, the engine has to assume one — so it stores the assumption and
labels every score built on it as provisional. This column lets the target be
a decision instead.

Revision ID: 0604d17f5e8e
Revises: e5c07a91f4b2
Create Date: 2026-08-17 18:37:12.302401
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types  # noqa: F401  (registers custom column types)


revision: str = '0604d17f5e8e'
down_revision: str | None = 'e5c07a91f4b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('icpc_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_rating', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('icpc_settings', schema=None) as batch_op:
        batch_op.drop_column('target_rating')

