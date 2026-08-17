"""Table grants for the authenticated role, and RLS for the ICPC tables

Two defects this fixes, both found only against a real Supabase instance:

1. **Missing GRANTs.** RLS policies filter rows *after* PostgreSQL checks
   table-level privileges. The earlier migration enabled RLS and wrote
   policies but never granted anything to `authenticated`, so every
   supabase-js query failed with `permission denied for table ...` — the
   policies never even got a chance to run. Local Postgres hid this because
   the test harness had already issued `ALTER DEFAULT PRIVILEGES`.

2. **ICPC tables locked out.** Supabase enables RLS on newly created tables,
   so the eight ICPC tables ended up with RLS on and zero policies — which
   denies everything to everyone.

Revision ID: c8a1f0b3e2d7
Revises: 7dbfc979dac3
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import app.db.types  # noqa: F401

revision: str = "c8a1f0b3e2d7"
down_revision: str | None = "7dbfc979dac3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ICPC tables scoped by a plain user_id column.
ICPC_USER_TABLES = [
    "icpc_settings",
    "icpc_topic_progress",
    "template_reviews",
    "virtual_contests",
    "practice_sessions",
    "hint_reveals",
    "readiness_snapshots",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    # -- grants ------------------------------------------------------------
    # Safe because RLS is enabled on every user table: the grant permits the
    # role to reach the table, and the policy still decides which rows.
    op.execute("GRANT USAGE ON SCHEMA public TO authenticated, anon, service_role")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO authenticated"
    )
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role")
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
        "TO authenticated, service_role"
    )
    # Future tables inherit the same treatment, so a later migration cannot
    # silently reintroduce the lockout.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon"
    )

    # `alembic_version` is migration bookkeeping, not user data. Supabase turns
    # RLS on for it; with no policy that is correct (nobody but the migration
    # role should read it), but revoke explicitly so intent is recorded.
    op.execute("REVOKE ALL ON TABLE alembic_version FROM authenticated, anon")

    # -- ICPC row-level security ------------------------------------------
    for table in ICPC_USER_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_owner_all ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_owner_all ON {table}
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid())
            """
        )

    # Contest problems carry no user_id; ownership flows through the contest.
    op.execute("ALTER TABLE virtual_contest_problems ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS virtual_contest_problems_owner_all "
        "ON virtual_contest_problems"
    )
    op.execute(
        """
        CREATE POLICY virtual_contest_problems_owner_all ON virtual_contest_problems
            FOR ALL TO authenticated
            USING (
                EXISTS (SELECT 1 FROM virtual_contests vc
                        WHERE vc.id = virtual_contest_problems.contest_id
                          AND vc.user_id = auth.uid())
            )
            WITH CHECK (
                EXISTS (SELECT 1 FROM virtual_contests vc
                        WHERE vc.id = virtual_contest_problems.contest_id
                          AND vc.user_id = auth.uid())
            )
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute(
        "DROP POLICY IF EXISTS virtual_contest_problems_owner_all "
        "ON virtual_contest_problems"
    )
    op.execute("ALTER TABLE virtual_contest_problems DISABLE ROW LEVEL SECURITY")
    for table in ICPC_USER_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner_all ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated, anon")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM authenticated"
    )
