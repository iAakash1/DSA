"""Admit takeuforward as a problem platform

211 of the 474 Striver A2Z entries have no LeetCode link — they are
takeUforward's own problems. They need a real platform value, so the
`problems.platform` vocabulary widens to admit it.

`submissions.platform` widens too, and not speculatively: a submission copies
its problem's platform, so recording a solve against any of those 211 problems
would otherwise fail the check constraint at the moment the user marks it
done.

`platform_accounts` and `contests` deliberately do NOT widen. There is no
takeUforward account to link and no takeUforward contest to enter, so the
narrower constraint is the correct one and keeps that impossible state
unrepresentable.

Revision ID: e5c07a91f4b2
Revises: d3d41b23022c
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import app.db.types  # noqa: F401

revision: str = "e5c07a91f4b2"
down_revision: str | None = "d3d41b23022c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables whose `platform` column may now hold a takeUforward problem.
_WIDENED = ("problems", "submissions")

_OLD = "'leetcode', 'codeforces'"
_NEW = "'leetcode', 'codeforces', 'takeuforward'"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _rewrite(values: str) -> None:
    for table in _WIDENED:
        name = f"ck_{table}_platform_valid"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK (platform IN ({values}))"
        )


def upgrade() -> None:
    # SQLite never carried these constraints (they are added by the Postgres
    # hardening migration), so there is nothing to rewrite there.
    if _is_postgres():
        _rewrite(_NEW)


def downgrade() -> None:
    if not _is_postgres():
        return
    # Narrowing again would fail while takeUforward rows exist. Remove their
    # memberships and problems first, or the constraint will refuse to apply —
    # which is the point: the data and the schema must agree.
    _rewrite(_OLD)
