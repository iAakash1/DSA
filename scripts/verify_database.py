#!/usr/bin/env python3
"""Verify the database matches what the application expects.

Run this after applying migrations to a Supabase project. On PostgreSQL it goes
further than "did the DDL run" and actually exercises row-level security by
assuming the `authenticated` role with a forged JWT claim, confirming that one
user genuinely cannot see another's rows.

Usage:
    python scripts/verify_database.py
    python scripts/verify_database.py --skip-rls
"""

from __future__ import annotations

import argparse
import sys
import uuid

import _bootstrap  # noqa: F401

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.bootstrap import check_schema
from app.db.session import engine
from app.models import Base

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

EXPECTED_RLS_TABLES = [
    "profiles",
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
    "collection_problems",
    "resources",
    "trusted_channels",
]


class Results:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        marker = PASS if ok else FAIL
        if not ok:
            self.failures += 1
        suffix = f"  {detail}" if detail else ""
        print(f"  [{marker}] {label}{suffix}")

    def skip(self, label: str, reason: str) -> None:
        print(f"  [{SKIP}] {label}  {reason}")


def verify_schema(results: Results) -> None:
    print("Schema")
    status = check_schema()
    results.check("database reachable", status.reachable, status.error or "")
    if not status.reachable:
        return
    results.check(
        "migrations at head",
        status.up_to_date,
        f"current={status.current_revision} head={status.head_revision}",
    )

    inspector = inspect(engine)
    actual = set(inspector.get_table_names())
    expected = set(Base.metadata.tables)
    missing = expected - actual
    results.check(
        f"all {len(expected)} tables present",
        not missing,
        f"missing: {sorted(missing)}" if missing else "",
    )


def verify_constraints(results: Results) -> None:
    print("\nConstraints and indexes")
    if not settings.is_postgres:
        results.skip("check constraints", "PostgreSQL only")
        results.skip("partial indexes", "PostgreSQL only")
        return

    with engine.connect() as conn:
        checks = conn.execute(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE contype = 'c' AND conname LIKE 'ck_%'"
            )
        ).scalar()
        results.check("check constraints installed", (checks or 0) >= 25, f"{checks} found")

        trgm = conn.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")
        ).scalar()
        results.check("pg_trgm extension", bool(trgm))

        partial = conn.execute(
            text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexdef LIKE '%WHERE%'"
            )
        ).scalar()
        results.check("partial indexes present", (partial or 0) >= 3, f"{partial} found")

        no_default = conn.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'id'
                  AND data_type = 'uuid' AND column_default IS NULL
                """
            )
        ).scalar()
        results.check(
            "uuid primary keys have defaults",
            (no_default or 0) == 0,
            f"{no_default} without default" if no_default else "",
        )


def verify_rls(results: Results, skip: bool) -> None:
    print("\nRow level security")
    if not settings.is_postgres:
        results.skip("RLS", "PostgreSQL only (SQLite enforces scoping in app code)")
        return
    if skip:
        results.skip("RLS", "--skip-rls")
        return

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename, rowsecurity FROM pg_tables "
                "WHERE schemaname = 'public'"
            )
        ).all()
        enabled = {name for name, secure in rows if secure}
        missing = [t for t in EXPECTED_RLS_TABLES if t not in enabled]
        results.check(
            f"RLS enabled on {len(EXPECTED_RLS_TABLES)} user tables",
            not missing,
            f"missing: {missing}" if missing else "",
        )

        policy_count = conn.execute(
            text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
        ).scalar()
        results.check("policies defined", (policy_count or 0) >= 40, f"{policy_count} found")

        unprotected = conn.execute(
            text(
                """
                SELECT t.tablename FROM pg_tables t
                WHERE t.schemaname = 'public'
                  AND t.rowsecurity = true
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_policies p
                      WHERE p.schemaname = 'public' AND p.tablename = t.tablename
                  )
                """
            )
        ).scalars().all()
        results.check(
            "no table has RLS on with zero policies",
            not unprotected,
            f"locked out: {list(unprotected)}" if unprotected else "",
        )

    _verify_isolation(results)


def _verify_isolation(results: Results) -> None:
    """Prove user A cannot read user B's rows through the authenticated role."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        with engine.begin() as conn:
            for user_id, name in ((user_a, "rls_probe_a"), (user_b, "rls_probe_b")):
                conn.execute(
                    text(
                        "INSERT INTO profiles (id, username, timezone, created_at, updated_at) "
                        "VALUES (:id, :username, 'UTC', now(), now()) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": str(user_id), "username": name},
                )

        with engine.connect() as conn:
            conn.execute(text("SET ROLE authenticated"))
            conn.execute(
                text("SELECT set_config('request.jwt.claims', :claims, true)"),
                {"claims": f'{{"sub":"{user_a}","role":"authenticated"}}'},
            )
            visible = conn.execute(
                text("SELECT count(*) FROM profiles WHERE id = :other"),
                {"other": str(user_b)},
            ).scalar()
            own = conn.execute(
                text("SELECT count(*) FROM profiles WHERE id = :self"),
                {"self": str(user_a)},
            ).scalar()
            conn.execute(text("RESET ROLE"))

        results.check("user cannot read another user's profile", visible == 0)
        results.check("user can read their own profile", own == 1)

    except Exception as exc:  # noqa: BLE001
        results.check("RLS isolation probe", False, str(exc)[:160])
    finally:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM profiles WHERE id = ANY(:ids)"),
                    {"ids": [str(user_a), str(user_b)]},
                )
        except Exception:  # noqa: BLE001 - cleanup is best effort
            pass


def verify_seed(results: Results) -> None:
    print("\nReference data")
    with engine.connect() as conn:
        for table, minimum, label in (
            ("topics", 50, "topic taxonomy"),
            ("patterns", 20, "patterns"),
            ("achievements", 20, "achievements"),
        ):
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0
            results.check(
                f"{label} seeded",
                count >= minimum,
                f"{count} rows" + ("" if count >= minimum else " — run: make seed"),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-rls", action="store_true")
    args = parser.parse_args()

    target = "PostgreSQL" if settings.is_postgres else "SQLite"
    print(f"Verifying CP-Forge database ({target})\n")

    results = Results()
    verify_schema(results)
    verify_constraints(results)
    verify_rls(results, args.skip_rls)
    verify_seed(results)

    print()
    if results.failures:
        print(f"{results.failures} check(s) failed.", file=sys.stderr)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
