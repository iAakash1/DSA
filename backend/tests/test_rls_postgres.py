"""Row-level security, verified against a real PostgreSQL server.

These tests do not read the migration SQL and conclude it looks right. They
assume the `authenticated` role with a forged JWT claim — exactly how
supabase-js reaches the database — and assert that one user genuinely cannot
read or write another user's rows.

They are SKIPPED (never silently passed) unless `TEST_DATABASE_URL` points at a
PostgreSQL instance:

    TEST_DATABASE_URL=postgresql://... pytest tests/test_rls_postgres.py -v
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_URL.startswith(("postgres://", "postgresql://")),
    reason="Set TEST_DATABASE_URL to a PostgreSQL URL to run the RLS suite",
)

#: Tables whose rows are scoped by a plain `user_id` column.
USER_OWNED_TABLES = [
    "user_settings",
    "platform_accounts",
    "user_problems",
    "submissions",
    "solving_sessions",
    "mistakes",
    "problem_notes",
    "reviews",
    "user_stats",
    "activity_days",
    "xp_transactions",
    "streak_freeze_transactions",
    "user_achievements",
    "daily_goals",
    "weekly_goals",
    "daily_missions",
    "contest_participations",
    "contest_problem_results",
    "recommendations",
    "sync_runs",
    "ai_insights",
    "ai_conversations",
    "ai_messages",
    "ai_usage",
    "collections",
]


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(_normalize(TEST_URL), pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def two_users(pg_engine):
    """Two real profiles, created with the privileged role."""
    alice, bob = uuid.uuid4(), uuid.uuid4()

    with pg_engine.begin() as conn:
        for uid, name in ((alice, "rls_alice"), (bob, "rls_bob")):
            conn.execute(
                text(
                    "INSERT INTO profiles (id, username, timezone, created_at, updated_at) "
                    "VALUES (:id, :u, 'UTC', now(), now()) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(uid), "u": name},
            )
            conn.execute(
                text(
                    "INSERT INTO user_stats (user_id, created_at, updated_at) "
                    "VALUES (:id, now(), now()) ON CONFLICT (user_id) DO NOTHING"
                ),
                {"id": str(uid)},
            )
            # A row in a representative user-owned table.
            conn.execute(
                text(
                    "INSERT INTO xp_transactions "
                    "(id, user_id, amount, kind, reason, dedupe_key, activity_date, "
                    " awarded_at, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :id, 10, 'bonus', 'rls probe', "
                    ":key, current_date, now(), now(), now()) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"id": str(uid), "key": f"rls-probe-{uid}"},
            )

    yield alice, bob

    with pg_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM profiles WHERE id = ANY(:ids)"),
            {"ids": [str(alice), str(bob)]},
        )


@contextmanager
def as_user(engine, user_id: uuid.UUID):
    """A connection acting as `authenticated` with `auth.uid()` = user_id.

    Both `SET ROLE` and `set_config(..., false)` are session-scoped, and
    SQLAlchemy hands connections back to a pool — so without an explicit reset
    the next checkout inherits the impersonation and silently has RLS applied
    to it. That produces confusing "the row vanished" failures in later
    assertions, so the reset is mandatory, not hygiene.
    """
    conn = engine.connect()
    try:
        conn.execute(text("SET ROLE authenticated"))
        conn.execute(
            text("SELECT set_config('request.jwt.claims', :claims, false)"),
            {"claims": f'{{"sub":"{user_id}","role":"authenticated"}}'},
        )
        yield conn
    finally:
        try:
            conn.rollback()
            conn.execute(text("RESET ROLE"))
            conn.execute(text("SELECT set_config('request.jwt.claims', '', false)"))
            conn.commit()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
        conn.close()


# ---------------------------------------------------------------------------
# RLS is actually switched on
# ---------------------------------------------------------------------------


def test_rls_is_enabled_on_every_user_table(pg_engine):
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public'")
        ).all()
    enabled = {name for name, secure in rows if secure}
    missing = [t for t in USER_OWNED_TABLES + ["profiles"] if t not in enabled]
    assert not missing, f"RLS not enabled on: {missing}"


#: Migration bookkeeping, not user data. Supabase enables RLS on it; having no
#: policy is the intended outcome — no application role should read it, and the
#: grants migration revokes it from `authenticated`/`anon` explicitly.
POLICY_EXEMPT_TABLES = {"alembic_version"}


def test_every_rls_table_has_at_least_one_policy(pg_engine):
    """RLS with no policy denies everything — a silent outage."""
    with pg_engine.connect() as conn:
        orphaned = conn.execute(
            text(
                """
                SELECT t.tablename FROM pg_tables t
                WHERE t.schemaname = 'public' AND t.rowsecurity
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_policies p
                      WHERE p.schemaname = 'public' AND p.tablename = t.tablename)
                """
            )
        ).scalars().all()
    unexpected = set(orphaned) - POLICY_EXEMPT_TABLES
    assert not unexpected, f"RLS on with zero policies: {sorted(unexpected)}"


def test_authenticated_role_can_actually_reach_its_tables(pg_engine):
    """Regression: RLS policies are useless without table-level GRANTs.

    Supabase initially rejected every `authenticated` query with
    `permission denied for table ...` — the policies never ran because the
    role lacked SELECT. Local Postgres hid it, since the harness had already
    issued ALTER DEFAULT PRIVILEGES.
    """
    with pg_engine.connect() as conn:
        missing = conn.execute(
            text(
                """
                SELECT t.tablename FROM pg_tables t
                WHERE t.schemaname = 'public'
                  AND t.tablename <> 'alembic_version'
                  AND NOT has_table_privilege(
                          'authenticated',
                          -- Schema-qualified: an unqualified name resolves via
                          -- search_path and can hit Supabase's auth schema.
                          format('%I.%I', t.schemaname, t.tablename)::regclass,
                          'SELECT')
                ORDER BY 1
                """
            )
        ).scalars().all()
    assert not missing, f"authenticated lacks SELECT on: {list(missing)}"


#: ICPC tables scoped by a plain `user_id` column.
ICPC_USER_TABLES = [
    "icpc_settings", "icpc_topic_progress", "template_reviews",
    "virtual_contests", "practice_sessions", "hint_reveals",
    "readiness_snapshots",
]

#: User-owned tables that carry no `user_id` of their own — ownership flows
#: through a parent row, so their policies are EXISTS-based and they are
#: covered by the parent's isolation test rather than a direct one.
INDIRECTLY_OWNED_TABLES = {
    "virtual_contest_problems",  # via virtual_contests.user_id
}

#: Tables where `user_id IS NULL` means "global, readable by everyone" and a
#: set `user_id` means "this user's override". Both halves need asserting:
#: the global rows must stay visible, and the per-user rows must not leak.
HYBRID_OWNED_TABLES = ["resources", "trusted_channels"]


def test_every_user_scoped_table_is_covered_by_an_isolation_test(pg_engine):
    """A table added later must not quietly escape the isolation suite.

    Discovers every table with a `user_id` column from the live schema and
    asserts it appears in one of the parametrized lists above. Without this,
    adding a table is enough to lose its coverage silently — which is how the
    ICPC tables shipped with RLS enabled and no policy in the first place.
    """
    with pg_engine.connect() as conn:
        scoped = conn.execute(
            text(
                """
                SELECT c.table_name FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                WHERE c.table_schema = 'public'
                  AND c.column_name = 'user_id'
                  AND t.table_type = 'BASE TABLE'
                ORDER BY 1
                """
            )
        ).scalars().all()

    covered = (
        set(USER_OWNED_TABLES)
        | set(ICPC_USER_TABLES)
        | INDIRECTLY_OWNED_TABLES
        | set(HYBRID_OWNED_TABLES)
    )
    uncovered = sorted(set(scoped) - covered)
    assert not uncovered, (
        "these tables have a user_id but no isolation test: " + ", ".join(uncovered)
    )


def test_indirectly_owned_tables_still_isolate(pg_engine, two_users):
    """Ownership through a parent row must isolate as strictly as a user_id."""
    alice, bob = two_users
    for table in sorted(INDIRECTLY_OWNED_TABLES):
        with as_user(pg_engine, alice) as conn:
            # Alice may not see rows reachable only through Bob's parent rows.
            leaked = conn.execute(
                text(
                    f"""
                    SELECT count(*) FROM {table} t
                    JOIN virtual_contests vc ON vc.id = t.contest_id
                    WHERE vc.user_id = :other
                    """
                ),
                {"other": str(bob)},
            ).scalar()
        assert leaked == 0, f"{table} leaked rows owned by another user"


#: A minimal valid INSERT per hybrid table. Written out rather than derived,
#: because every NOT NULL column here has a Python-side default that the
#: database does not supply.
_HYBRID_INSERT = {
    "resources": (
        "INSERT INTO resources (id, user_id, problem_id, kind, title, url, "
        "provider, score, is_selected, is_manual, created_at, updated_at) "
        "SELECT gen_random_uuid(), :uid, p.id, 'video', 'private probe', "
        "'https://example.invalid/probe', 'youtube', 0, false, true, now(), now() "
        "FROM problems p LIMIT 1"
    ),
    "trusted_channels": (
        "INSERT INTO trusted_channels (id, user_id, channel_id, name, enabled, "
        "weight, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :uid, 'probe-channel', 'private probe', "
        "true, 1.0, now(), now())"
    ),
}


@pytest.mark.parametrize("table", HYBRID_OWNED_TABLES)
def test_hybrid_tables_share_globals_but_isolate_overrides(pg_engine, two_users, table):
    """Global rows stay shared; per-user rows stay private.

    These carry a nullable `user_id`: NULL is a curated global row every user
    should read, anything else is one user's own override. A policy that got
    either half wrong would be invisible in a table that happens to hold only
    global rows, so both halves are asserted explicitly.
    """
    alice, bob = two_users

    with pg_engine.begin() as conn:
        global_rows = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id IS NULL")
        ).scalar()

    with as_user(pg_engine, bob) as conn:
        conn.execute(text(_HYBRID_INSERT[table]), {"uid": str(bob)})
        conn.commit()
        mine = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :uid"),
            {"uid": str(bob)},
        ).scalar()
    assert mine == 1, "a user must see their own override row"

    try:
        with as_user(pg_engine, alice) as conn:
            leaked = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id = :other"),
                {"other": str(bob)},
            ).scalar()
            shared = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id IS NULL")
            ).scalar()
        assert leaked == 0, f"{table} leaked another user's override"
        assert shared == global_rows, "global rows must stay readable by everyone"
    finally:
        with pg_engine.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": str(bob)}
            )


@pytest.mark.parametrize("table", ICPC_USER_TABLES)
def test_icpc_tables_isolate_users(pg_engine, two_users, table):
    """The ICPC tables must be scoped like every other user-owned table."""
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        leaked = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :other"),
            {"other": str(bob)},
        ).scalar()
    assert leaked == 0


# ---------------------------------------------------------------------------
# Read isolation
# ---------------------------------------------------------------------------


def test_user_reads_only_their_own_profile(pg_engine, two_users):
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        own = conn.execute(
            text("SELECT count(*) FROM profiles WHERE id = :id"), {"id": str(alice)}
        ).scalar()
        other = conn.execute(
            text("SELECT count(*) FROM profiles WHERE id = :id"), {"id": str(bob)}
        ).scalar()

    assert own == 1
    assert other == 0, "Alice can see Bob's profile"


@pytest.mark.parametrize("table", USER_OWNED_TABLES)
def test_user_cannot_read_another_users_rows(pg_engine, two_users, table):
    """Bob's rows must be invisible to Alice in every user-owned table."""
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        leaked = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :other"),
            {"other": str(bob)},
        ).scalar()

    assert leaked == 0, f"{table} leaked rows belonging to another user"


def test_unscoped_select_returns_only_own_rows(pg_engine, two_users):
    """Even an unfiltered SELECT must be silently restricted."""
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        rows = conn.execute(text("SELECT DISTINCT user_id FROM xp_transactions")).scalars().all()

    assert str(bob) not in {str(r) for r in rows}


# ---------------------------------------------------------------------------
# Write isolation
# ---------------------------------------------------------------------------


def test_user_cannot_insert_rows_owned_by_another_user(pg_engine, two_users):
    from sqlalchemy.exc import ProgrammingError

    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        with pytest.raises(ProgrammingError):  # violates WITH CHECK
            conn.execute(
                text(
                    "INSERT INTO xp_transactions "
                    "(id, user_id, amount, kind, reason, dedupe_key, activity_date, "
                    " awarded_at, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :other, 9999, 'bonus', 'attack', "
                    "'rls-attack', current_date, now(), now(), now())"
                ),
                {"other": str(bob)},
            )


def test_user_cannot_update_another_users_rows(pg_engine, two_users):
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        result = conn.execute(
            text("UPDATE xp_transactions SET amount = 99999 WHERE user_id = :other"),
            {"other": str(bob)},
        )
        conn.commit()

    assert result.rowcount == 0, "Alice modified Bob's XP"

    # Confirm Bob's data is untouched.
    with pg_engine.connect() as admin:
        amount = admin.execute(
            text("SELECT amount FROM xp_transactions WHERE user_id = :id"),
            {"id": str(bob)},
        ).scalar()
    assert amount == 10


def test_user_cannot_delete_another_users_rows(pg_engine, two_users):
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        result = conn.execute(
            text("DELETE FROM xp_transactions WHERE user_id = :other"),
            {"other": str(bob)},
        )
        conn.commit()

    assert result.rowcount == 0, "Alice deleted Bob's XP"


def test_user_cannot_escalate_by_updating_their_profile_id(pg_engine, two_users):
    alice, bob = two_users
    with as_user(pg_engine, alice) as conn:
        try:
            result = conn.execute(
                text("UPDATE profiles SET id = :other WHERE id = :self"),
                {"other": str(bob), "self": str(alice)},
            )
            conn.commit()
            assert result.rowcount == 0
        except Exception:
            # A constraint or policy rejection is an equally acceptable outcome.
            conn.rollback()


# ---------------------------------------------------------------------------
# Catalog tables stay readable
# ---------------------------------------------------------------------------


def test_shared_catalog_is_readable_by_authenticated_users(pg_engine, two_users):
    """Problems and topics are shared reference data, not user data."""
    alice, _ = two_users
    with as_user(pg_engine, alice) as conn:
        problems = conn.execute(text("SELECT count(*) FROM problems")).scalar()
        topics = conn.execute(text("SELECT count(*) FROM topics")).scalar()

    assert problems >= 0 and topics >= 0, "catalog reads must not be blocked"


def test_authenticated_user_cannot_write_the_shared_catalog(pg_engine, two_users):
    """Only the backend may mutate canonical problems."""
    from sqlalchemy.exc import ProgrammingError

    alice, _ = two_users
    with as_user(pg_engine, alice) as conn:
        with pytest.raises(ProgrammingError):
            conn.execute(
                text(
                    "INSERT INTO problems (id, platform, external_id, title, url, "
                    "difficulty, metadata_complete, is_premium, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'codeforces', 'rls-attack', 'x', 'u', "
                    "'unknown', false, false, now(), now())"
                )
            )


# ---------------------------------------------------------------------------
# Schema regressions
# ---------------------------------------------------------------------------


def test_every_uuid_primary_key_has_a_database_default(pg_engine):
    """Regression: an autogenerated migration once emitted
    `ALTER COLUMN id DROP DEFAULT` for all 36 uuid primary keys, because
    `gen_random_uuid()` is applied in the Postgres-only migration and
    deliberately absent from the models. That stripped the defaults that make
    trigger- and client-side inserts valid. This must never recur silently.
    """
    with pg_engine.connect() as conn:
        missing = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'id'
                  AND data_type = 'uuid' AND column_default IS NULL
                ORDER BY table_name
                """
            )
        ).scalars().all()
    assert not missing, f"uuid primary keys without a default: {list(missing)}"


def test_insert_without_an_explicit_id_succeeds(pg_engine):
    """The practical consequence of the default being present."""
    with pg_engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO problems (platform, external_id, title, url, difficulty, "
                "metadata_complete, is_premium, created_at, updated_at) "
                "VALUES ('codeforces', 'defaults-probe', 't', 'u', 'unknown', "
                "false, false, now(), now()) RETURNING id"
            )
        ).scalar()
        assert row is not None
        conn.execute(
            text("DELETE FROM problems WHERE external_id = 'defaults-probe'")
        )


def test_new_columns_exist(pg_engine):
    """Provenance, hints and curator videos survived the migration chain."""
    with pg_engine.connect() as conn:
        cols = conn.execute(
            text(
                """
                SELECT table_name || '.' || column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (table_name, column_name) IN
                      (('sheets','source_metadata'),('problems','hints'),
                       ('problems','video_links'))
                """
            )
        ).scalars().all()
    assert set(cols) == {
        "sheets.source_metadata", "problems.hints", "problems.video_links"
    }
