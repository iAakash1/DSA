"""Every platform CHECK constraint, verified against a real PostgreSQL server.

These constraints do not exist on SQLite, so the main suite cannot see them.
That gap is exactly how a platform once shipped accepted by `problems` and
rejected by `submissions` — the failure surfaced only when a user recorded a
solve, in production.

So this test does not read the migration and conclude it looks right. It
discovers every platform CHECK from `pg_constraint` and asserts each one
admits the full vocabulary, which means a table added later with a narrower
constraint fails here rather than in front of a user.

SKIPPED (never silently passed) without a PostgreSQL `TEST_DATABASE_URL`.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.models.enums import CONNECTABLE_PLATFORMS, ContestPlatform, Platform

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_URL.startswith(("postgres://", "postgresql://")),
    reason="Set TEST_DATABASE_URL to a PostgreSQL URL to run the constraint suite",
)

#: Which vocabulary each table's constraint must admit. Tables differ on
#: purpose, not by oversight: there is no takeUforward account to link and no
#: takeUforward contest to enter.
EXPECTED: dict[str, set[str]] = {
    "problems": {p.value for p in Platform},
    "submissions": {p.value for p in Platform},
    "platform_accounts": {p.value for p in CONNECTABLE_PLATFORMS},
    "contests": {p.value for p in ContestPlatform},
}


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_normalize(TEST_URL), pool_pre_ping=True)
    yield eng
    eng.dispose()


def test_every_platform_check_is_discovered(engine):
    """The set of tables carrying a platform CHECK must be the set we expect.

    A new table with a platform column and a narrow constraint would otherwise
    go unnoticed until something failed to insert into it.
    """
    with engine.connect() as conn:
        found = conn.execute(
            text(
                """
                SELECT rel.relname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = rel.relnamespace
                WHERE n.nspname = 'public' AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) LIKE '%codeforces%'
                """
            )
        ).scalars().all()
    assert set(found) == set(EXPECTED), (
        "platform CHECK constraints changed; update EXPECTED deliberately"
    )


@pytest.mark.parametrize("table", sorted(EXPECTED))
def test_constraint_admits_every_expected_platform(engine, table):
    with engine.connect() as conn:
        definition = conn.execute(
            text(
                """
                SELECT pg_get_constraintdef(con.oid)
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = :table AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) LIKE '%codeforces%'
                """
            ),
            {"table": table},
        ).scalar_one()

    missing = [p for p in EXPECTED[table] if f"'{p}'" not in definition]
    assert not missing, f"{table} rejects {missing}"


def test_a_problem_and_its_submission_accept_the_same_platforms(engine):
    """The regression that caused the original bug, in one test.

    A platform accepted by `problems` but rejected by `submissions` is invisible
    until someone records a solve. Inserting both, for every platform, is the
    only check that actually covers it.
    """
    for platform in sorted({p.value for p in Platform}):
        marker = uuid.uuid4().hex[:10]
        with engine.begin() as conn:
            problem_id = conn.execute(
                text(
                    """
                    INSERT INTO problems (id, platform, external_id, title, url,
                                          difficulty, is_premium, metadata_complete,
                                          created_at, updated_at)
                    VALUES (gen_random_uuid(), :p, :ext, 'constraint probe',
                            'https://example.invalid/probe', 'unknown', false, false,
                            now(), now())
                    RETURNING id
                    """
                ),
                {"p": platform, "ext": f"probe-{marker}"},
            ).scalar_one()

            user_id = conn.execute(
                text("SELECT id FROM profiles ORDER BY created_at LIMIT 1")
            ).scalar()
            if user_id is not None:
                conn.execute(
                    text(
                        """
                        INSERT INTO submissions (id, user_id, problem_id, platform,
                                                 verdict, is_accepted, submitted_at,
                                                 source, during_contest,
                                                 created_at, updated_at)
                        VALUES (gen_random_uuid(), :u, :prob, :p, 'OK', true, now(),
                                'manual', false, now(), now())
                        """
                    ),
                    {"u": user_id, "prob": problem_id, "p": platform},
                )
                conn.execute(
                    text("DELETE FROM submissions WHERE problem_id = :prob"),
                    {"prob": problem_id},
                )
            conn.execute(text("DELETE FROM problems WHERE id = :id"), {"id": problem_id})


def test_a_connectable_platform_can_actually_be_connected(engine):
    """Every platform the API offers must survive the insert.

    `platform_accounts` carried the narrowest constraint of the four, so
    CodeChef and AtCoder could be offered by the API and then rejected by the
    database — the same class of bug, one table over.
    """
    with engine.begin() as conn:
        user_id = conn.execute(
            text("SELECT id FROM profiles ORDER BY created_at LIMIT 1")
        ).scalar()
    if user_id is None:
        pytest.skip("no profile exists to attach a platform account to")

    for platform in sorted({p.value for p in CONNECTABLE_PLATFORMS}):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO platform_accounts (id, user_id, platform, username,
                                                   connected, created_at, updated_at)
                    VALUES (gen_random_uuid(), :u, :p, :name, true, now(), now())
                    ON CONFLICT (user_id, platform) DO NOTHING
                    """
                ),
                {"u": user_id, "p": platform, "name": f"probe-{platform}"},
            )
            conn.execute(
                text(
                    "DELETE FROM platform_accounts "
                    "WHERE user_id = :u AND platform = :p AND username = :name"
                ),
                {"u": user_id, "p": platform, "name": f"probe-{platform}"},
            )


def test_an_unknown_platform_is_still_rejected(engine):
    """Widening must not have turned the constraint into a formality."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO problems (id, platform, external_id, title, url,
                                          difficulty, is_premium, metadata_complete,
                                          created_at, updated_at)
                    VALUES (gen_random_uuid(), 'not-a-platform', 'x', 't',
                            'https://example.invalid/x', 'unknown', false, false,
                            now(), now())
                    """
                )
            )
