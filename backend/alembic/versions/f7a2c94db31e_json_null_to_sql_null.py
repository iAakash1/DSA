"""Normalise JSON `null` in jsonb columns to SQL NULL

SQLAlchemy's JSONB type stores Python `None` as the JSON value `null` unless
`none_as_null=True` is set — which it was not. The result is that every
"unset" jsonb column holds a JSON scalar rather than SQL NULL, so
`column.is_(None)` matches nothing on Postgres while behaving correctly on
SQLite. A SQLite test suite cannot see the difference.

The type is fixed for new writes; this migration repairs the rows already
written. It walks every jsonb column in the schema rather than naming them, so
columns added between this migration and its author's knowledge are covered
too.

Revision ID: f7a2c94db31e
Revises: 0604d17f5e8e
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import app.db.types  # noqa: F401

revision: str = "f7a2c94db31e"
down_revision: str | None = "0604d17f5e8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        DO $$
        DECLARE
            target record;
        BEGIN
            FOR target IN
                SELECT c.table_name, c.column_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema
                 AND t.table_name = c.table_name
                WHERE c.table_schema = 'public'
                  AND c.data_type = 'jsonb'
                  AND c.is_nullable = 'YES'
                  AND t.table_type = 'BASE TABLE'
            LOOP
                EXECUTE format(
                    'UPDATE public.%I SET %I = NULL '
                    'WHERE %I IS NOT NULL AND jsonb_typeof(%I) = ''null''',
                    target.table_name, target.column_name,
                    target.column_name, target.column_name
                );
            END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    # Deliberately not reversible: rewriting SQL NULL back to JSON `null` would
    # reintroduce the bug and cannot distinguish rows that were always NULL.
    pass
