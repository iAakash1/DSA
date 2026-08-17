"""Admit CodeChef and AtCoder, and give platform accounts real statistics

Two things, both additive.

**Statistics on `platform_accounts`.** The table already carried rating and
max rating; connected profiles also need rank, solved count, contest count and
a difficulty breakdown. All nullable, because null here means "this platform
does not expose it" — which is not the same as zero, and is rendered as
Unavailable rather than as a number.

**Four widened CHECK constraints.** Every constraint in the schema that
enumerates platform values was found by querying `pg_constraint` rather than
by reading migrations, because reading migrations is how the last one got
missed:

  problems           leetcode, codeforces, takeuforward   -> + codechef, atcoder
  submissions        leetcode, codeforces, takeuforward   -> + codechef, atcoder
  platform_accounts  leetcode, codeforces                 -> + codechef, atcoder
  contests           leetcode, codeforces, codechef       -> + atcoder

`submissions` is the one that broke last time: a platform accepted by
`problems` but rejected by `submissions` fails at the moment a user records a
solve, not at import. `platform_accounts` was the same trap one table over —
at its old width, connecting a CodeChef or AtCoder profile would have failed
outright.

`takeuforward` keeps its place on `problems`/`submissions` and stays absent
from `platform_accounts`/`contests`: there is no takeUforward account to link
and no takeUforward contest to enter. Widening cannot invalidate an existing
row, so no data is touched.

Revision ID: a4e91c6b7d20
Revises: 21593fe33ec1
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types  # noqa: F401  (registers custom column types)

revision: str = "a4e91c6b7d20"
down_revision: str | None = "21593fe33ec1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: table -> (allowed before, allowed after). Every platform CHECK in the
#: schema, enumerated so the pairs are reviewable side by side.
_PLATFORM_CHECKS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "problems": (
        ("leetcode", "codeforces", "takeuforward"),
        ("leetcode", "codeforces", "takeuforward", "codechef", "atcoder"),
    ),
    "submissions": (
        ("leetcode", "codeforces", "takeuforward"),
        ("leetcode", "codeforces", "takeuforward", "codechef", "atcoder"),
    ),
    "platform_accounts": (
        ("leetcode", "codeforces"),
        ("leetcode", "codeforces", "codechef", "atcoder"),
    ),
    "contests": (
        ("leetcode", "codeforces", "codechef"),
        ("leetcode", "codeforces", "codechef", "atcoder"),
    ),
}

_NEW_COLUMNS = (
    ("rank", sa.String(length=64)),
    ("problems_solved", sa.Integer()),
    ("contests_participated", sa.Integer()),
    ("difficulty_breakdown", app.db.types.JSONType()),
    ("stat_provenance", app.db.types.JSONType()),
)


def _quote(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _apply_checks(index: int) -> None:
    """Rewrite every platform CHECK to the vocabulary at `index` of the pairs."""
    for table, versions in _PLATFORM_CHECKS.items():
        name = f"ck_{table}_platform_valid"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK (platform IN ({_quote(versions[index])}))"
        )


def upgrade() -> None:
    with op.batch_alter_table("platform_accounts", schema=None) as batch_op:
        for name, type_ in _NEW_COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))

    # SQLite never carried these constraints — they are added by the Postgres
    # hardening migration — so there is nothing to rewrite there.
    if op.get_bind().dialect.name == "postgresql":
        _apply_checks(1)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Narrowing fails while codechef/atcoder rows exist, and that is the
        # correct outcome: remove the data first, or the schema and its
        # contents would disagree.
        _apply_checks(0)

    with op.batch_alter_table("platform_accounts", schema=None) as batch_op:
        for name, _ in reversed(_NEW_COLUMNS):
            batch_op.drop_column(name)
