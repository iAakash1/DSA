#!/usr/bin/env python3
"""Validate imported sheets against their expected shape.

This exists so "CP-31 is imported" can never be claimed on the strength of a
partial, hand-curated file. CP-31 is 31 problems per rating category; if the
database holds fewer, this reports the exact shortfall per bucket and exits
non-zero.

    python scripts/validate_sheets.py
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401

from sqlalchemy import func, select

from app.db.session import session_scope
from app.models.problem import Problem
from app.models.sheet import Sheet, SheetProblem, SheetSection

#: CP-31 structure, read from the signed-in sheet page at
#: https://www.tle-eliminators.com/cp-sheet — 12 rating buckets (800-1900),
#: 31 problems each, "Overall Progress 0/372". These are observed values, not
#: assumptions.
CP31_PER_BUCKET = 31
CP31_BUCKETS = [800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900]
CP31_EXPECTED_TOTAL = CP31_PER_BUCKET * len(CP31_BUCKETS)  # 372

#: An authoritative export dropped here replaces the partial development seed.
AUTHORITATIVE_SOURCE = "data/sources/cp31.json"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"


def validate_cp31(db) -> bool:
    sheet = db.scalar(select(Sheet).where(Sheet.slug == "cp31"))
    if sheet is None:
        print(f"  [{FAIL}] CP-31 has not been imported at all")
        return False

    rows = db.execute(
        select(SheetSection.name, SheetSection.rating_bucket, func.count(SheetProblem.id))
        .outerjoin(SheetProblem, SheetProblem.section_id == SheetSection.id)
        .where(SheetSection.sheet_id == sheet.id)
        .group_by(SheetSection.name, SheetSection.rating_bucket)
        .order_by(SheetSection.rating_bucket)
    ).all()

    from app.core.config import REPO_ROOT

    total = sum(int(c) for _, _, c in rows)
    expected = CP31_EXPECTED_TOTAL
    has_source = (REPO_ROOT / AUTHORITATIVE_SOURCE).exists()

    if not has_source:
        print(f"  [{WARN}] CP-31 authoritative source not imported — corpus "
              "completeness cannot be established.")
        print(f"         (no {AUTHORITATIVE_SOURCE}; using the PARTIAL "
              "development seed)")
        print()

    print(f"  CP-31: {total} problems across {len(rows)} rating categories")
    print(f"  Authoritative sheet: {CP31_PER_BUCKET} x {len(CP31_BUCKETS)} buckets "
          f"= {expected}")
    print()
    print(f"  {'bucket':<10}{'have':>6}{'need':>6}{'gap':>6}")
    complete = True
    for name, _bucket, count in rows:
        count = int(count)
        gap = max(0, CP31_PER_BUCKET - count)
        if gap:
            complete = False
        print(f"  {name:<10}{count:>6}{CP31_PER_BUCKET:>6}{gap:>6}")

    print()
    if complete:
        print(f"  [{PASS}] every category holds {CP31_PER_BUCKET} problems")
    else:
        missing = expected - total
        status = "PARTIAL (development data)" if not has_source else "INCOMPLETE"
        print(f"  [{FAIL}] CP-31 is {status} — {missing} problems missing "
              f"({total}/{expected})")
        print()
        print("  The bundled data/seed/cp31.json is a PARTIAL development set,")
        print("  NOT the authoritative sheet. To complete it, drop the real")
        print("  export at data/imports/cp31.json in this shape:")
        print()
        print('      {"sheet": {"slug": "cp31", "name": "CP-31", "kind": "cp31"},')
        print('       "sections": [{"slug": "800", "name": "800",')
        print('                     "kind": "rating_bucket", "rating_bucket": 800}],')
        print('       "problems": [{"platform": "codeforces",')
        print('                     "external_id": "4A", "section": "800"}]}')
        print()
        print("  then run:  python scripts/import_cp31.py --source data/sources/cp31.json")
        print("  Ratings, titles and tags are fetched from the Codeforces API,")
        print("  so only the problem ids and their category are required.")
    return complete


def validate_striver(db) -> bool:
    sheet = db.scalar(select(Sheet).where(Sheet.slug == "striver-a2z"))
    if sheet is None:
        print(f"  [{FAIL}] Striver A2Z has not been imported at all")
        return False

    rows = db.execute(
        select(SheetSection.name, func.count(SheetProblem.id))
        .outerjoin(SheetProblem, SheetProblem.section_id == SheetSection.id)
        .where(SheetSection.sheet_id == sheet.id)
        .group_by(SheetSection.name, SheetSection.sort_order)
        .order_by(SheetSection.sort_order)
    ).all()

    total = sum(int(c) for _, c in rows)
    empty = [name for name, count in rows if int(count) == 0]

    print(f"  Striver A2Z: {total} problems across {len(rows)} sections")
    for name, count in rows:
        print(f"    {name:<32}{int(count):>4}")
    print()

    # The published A2Z sheet is ~450 problems; anything far below that is a
    # partial import, not a complete one.
    if total < 400:
        print(f"  [{WARN}] Striver A2Z holds {total} problems. The published "
              "sheet is ~450+.")
        print("  The bundled file is a curated subset covering every section,")
        print("  not the full sheet. Drop the real export at")
        print("  data/imports/striver.json and run scripts/import_striver.py.")
        return False
    if empty:
        print(f"  [{FAIL}] sections with no problems: {empty}")
        return False
    print(f"  [{PASS}] Striver A2Z looks complete")
    return True


def validate_canonical(db) -> bool:
    """No sheet membership may have created a duplicate canonical problem."""
    dupes = db.execute(
        select(Problem.platform, Problem.external_id, func.count(Problem.id))
        .group_by(Problem.platform, Problem.external_id)
        .having(func.count(Problem.id) > 1)
    ).all()
    orphans = db.scalar(
        select(func.count(SheetProblem.id)).outerjoin(
            Problem, Problem.id == SheetProblem.problem_id
        ).where(Problem.id.is_(None))
    )

    print(f"  duplicate canonical ids: {len(dupes)}")
    print(f"  sheet rows with no problem: {orphans}")
    ok = not dupes and not orphans
    print(f"  [{PASS if ok else FAIL}] canonical integrity")
    return ok


def main() -> int:
    print("Validating imported sheets\n")
    with session_scope() as db:
        print("CP-31")
        cp31_ok = validate_cp31(db)
        print("\nStriver A2Z")
        striver_ok = validate_striver(db)
        print("\nCanonical integrity")
        canonical_ok = validate_canonical(db)

    print()
    if cp31_ok and striver_ok and canonical_ok:
        print("All sheets validated.")
        return 0
    print("Sheet data is incomplete — see the instructions above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
