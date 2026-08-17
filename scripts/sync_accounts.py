#!/usr/bin/env python3
"""Sync connected platform accounts from the command line.

    python scripts/sync_accounts.py                 # every connected account
    python scripts/sync_accounts.py --platform codeforces

Upstream outages are reported, not raised — existing data is never touched.
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401

from sqlalchemy import select

from app.db.session import session_scope
from app.models.user import PlatformAccount, Profile
from app.services.solve_service import recompute_user_state
from app.services.sync_service import sync_account


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["codeforces", "leetcode"])
    parser.add_argument("--user", help="Profile id (defaults to every profile).")
    args = parser.parse_args()

    with session_scope() as db:
        query = select(PlatformAccount).where(PlatformAccount.connected.is_(True))
        if args.platform:
            query = query.where(PlatformAccount.platform == args.platform)
        if args.user:
            query = query.where(PlatformAccount.user_id == args.user)
        accounts = [(a.user_id, a.platform, a.username) for a in db.scalars(query).all()]

        if not accounts:
            profiles = db.scalar(select(Profile).limit(1))
            if profiles is None:
                print(
                    "No profiles exist yet. Start the app and open the dashboard once, "
                    "then connect your handles in Settings.",
                    file=sys.stderr,
                )
            else:
                print(
                    "No connected accounts. Add your handles in Settings, or set "
                    "CODEFORCES_HANDLE / LEETCODE_USERNAME in .env.",
                    file=sys.stderr,
                )
            return 1

    failures = 0
    touched: set = set()
    for user_id, platform, username in accounts:
        with session_scope() as db:
            result = sync_account(db, user_id, platform)
        touched.add(user_id)
        if result.status == "success":
            print(
                f"{platform:<11} {username:<20} "
                f"fetched={result.submissions_fetched} new={result.submissions_new} "
                f"solved={result.problems_solved} xp={result.xp_awarded}"
            )
            if result.details.get("note"):
                print(f"            note: {result.details['note']}")
        else:
            failures += 1
            print(f"{platform:<11} {username:<20} FAILED: {result.error}", file=sys.stderr)
            if result.last_success:
                print(f"            last successful sync: {result.last_success}", file=sys.stderr)

    for user_id in touched:
        with session_scope() as db:
            state = recompute_user_state(db, user_id)
        print(f"\nStreak: {state['streak']} (longest {state['longest_streak']})")
        if state["achievements_unlocked"]:
            print(f"Unlocked: {', '.join(state['achievements_unlocked'])}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
