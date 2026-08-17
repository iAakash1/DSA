#!/usr/bin/env python3
"""Seed reference data and import the bundled sheets.

Reference data (topic taxonomy, patterns, achievements) lives in Python because
it is behaviour, not user content — the achievement criteria are evaluated by
the engine, so definitions and evaluation stay in one place.

Everything here is idempotent. Run it as often as you like.

Usage:
    python scripts/seed_database.py                 # taxonomy + achievements + sheets
    python scripts/seed_database.py --no-sheets     # reference data only
    python scripts/seed_database.py --offline       # skip platform metadata lookups
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401  (sets sys.path)

from app.core.config import REPO_ROOT, settings
from app.db.bootstrap import check_schema
from app.db.session import session_scope
from app.gamification.achievements import seed_achievements
from app.services.import_service import import_from_path
from app.services.taxonomy import seed_taxonomy

SHEETS = [
    ("CP-31", REPO_ROOT / "data" / "seed" / "cp31.json"),
    ("Striver A2Z", REPO_ROOT / "data" / "seed" / "striver_a2z.json"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-sheets", action="store_true", help="Skip sheet imports.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not contact Codeforces/LeetCode for metadata.",
    )
    args = parser.parse_args()

    status = check_schema()
    if not status.reachable:
        print(f"Database unreachable: {status.error}", file=sys.stderr)
        return 1
    if not status.up_to_date:
        print(
            "Database schema is not at head. Run:\n"
            "  cd backend && alembic upgrade head",
            file=sys.stderr,
        )
        return 1

    target = "PostgreSQL" if settings.is_postgres else "SQLite"
    print(f"Seeding {target} (revision {status.current_revision})\n")

    with session_scope() as db:
        taxonomy = seed_taxonomy(db)
        print(
            f"Taxonomy    topics +{taxonomy['topics_created']} "
            f"(updated {taxonomy['topics_updated']}), "
            f"patterns +{taxonomy['patterns_created']}"
        )

        created = seed_achievements(db)
        print(f"Achievements +{created}")

    if args.no_sheets:
        print("\nSkipped sheet imports (--no-sheets).")
        return 0

    print()
    failed = False
    for name, path in SHEETS:
        if not path.exists():
            print(f"{name}: seed file missing at {path}", file=sys.stderr)
            failed = True
            continue
        with session_scope() as db:
            report = import_from_path(db, path, enrich=not args.offline)
        print(f"{name}: {report.summary()}")
        for warning in report.warnings[:5]:
            print(f"  warning: {warning}")
        for error in report.errors[:10]:
            print(f"  error:   {error}")
            failed = True

    print("\nDone." if not failed else "\nCompleted with errors.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
