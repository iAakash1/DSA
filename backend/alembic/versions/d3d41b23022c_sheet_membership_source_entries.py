"""Keep every source row behind a collapsed sheet membership

A sheet may list one canonical problem more than once. Striver A2Z reaches
`rotate-array` twice ("Left Rotate Array by One", "…by K Places") and
`binary-tree-inorder-traversal` four times, because takeUforward points several
distinct exercises at the same LeetCode problem.

Progress has to collapse onto the canonical problem — otherwise solving it once
leaves a phantom unsolved twin — but the rows are genuinely different
exercises, so discarding them would quietly shrink the sheet from 474 entries
to 455. They are kept on the membership instead.

Revision ID: d3d41b23022c
Revises: c8a1f0b3e2d7
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types  # custom column types referenced below

revision: str = "d3d41b23022c"
down_revision: str | None = "c8a1f0b3e2d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sheet_problems", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source_entries", app.db.types.JSONType(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("sheet_problems", schema=None) as batch_op:
        batch_op.drop_column("source_entries")
