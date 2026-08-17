#!/usr/bin/env python3
"""Full corpus verification against whatever database is configured.

Prints a per-section reconciliation for every sheet and a set of PASS/FAIL
checks. Run it before and after a re-import to prove idempotency:

    python scripts/verify_corpora.py --json before.json
    python scripts/import_striver.py --offline --reconcile
    python scripts/verify_corpora.py --json after.json --compare before.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401

from app.db.session import session_scope
from sqlalchemy import func, select

from app.models.problem import Problem, ProblemTopic
from app.models.sheet import Sheet, SheetProblem, SheetSection

#: Per-step counts the takeUforward sheet page displays. Independent of
#: anything stored in the database — this is the external ground truth.
STRIVER_EXPECTED = {
    "step-01-basics": 54, "step-02-sorting": 7, "step-03-arrays": 40,
    "step-04-binary-search": 32, "step-05-strings": 15, "step-06-linked-list": 31,
    "step-07-recursion": 25, "step-08-bit-manipulation": 18, "step-09-stack-queue": 30,
    "step-10-sliding-window": 12, "step-11-heaps": 17, "step-12-greedy": 15,
    "step-13-binary-trees": 38, "step-14-bst": 16, "step-15-graphs": 53,
    "step-16-dynamic-programming": 55, "step-17-tries": 7, "step-18-strings-advanced": 9,
}
STRIVER_SOURCE_ROWS = sum(STRIVER_EXPECTED.values())   # 474
STRIVER_CANONICAL = 455
CP31_PROBLEMS = 372
#: CP-31 is 31 problems in each of 12 rating bands, 800 through 1900.
CP31_BUCKETS = list(range(800, 2000, 100))
CP31_PER_BUCKET = 31


def collect(db) -> dict:
    out: dict = {"sheets": {}}
    for sheet in db.scalars(select(Sheet).order_by(Sheet.slug)):
        links = db.scalars(
            select(SheetProblem).where(SheetProblem.sheet_id == sheet.id)
        ).all()
        sections = db.scalars(
            select(SheetSection)
            .where(SheetSection.sheet_id == sheet.id)
            .order_by(SheetSection.sort_order)
        ).all()

        entries_by_section: Counter = Counter()
        memberships_by_section: Counter = Counter()
        section_slug = {s.id: s.slug for s in sections}
        total_entries = 0
        missing_entries = 0
        for link in links:
            memberships_by_section[section_slug.get(link.section_id, "<none>")] += 1
            rows = link.source_entries or []
            if not rows:
                missing_entries += 1
            for entry in rows:
                entries_by_section[entry.get("section", "<none>")] += 1
                total_entries += 1

        problem_ids = [link.problem_id for link in links]
        problems = (
            db.scalars(select(Problem).where(Problem.id.in_(problem_ids))).all()
            if problem_ids
            else []
        )
        out["sheets"][sheet.slug] = {
            "memberships": len(links),
            "sections": len(sections),
            "source_entries": total_entries,
            "memberships_without_entries": missing_entries,
            "entries_by_section": dict(entries_by_section),
            "memberships_by_section": dict(memberships_by_section),
            "duplicate_memberships": len(links) - len({link.problem_id for link in links}),
            "duplicate_orders": len(links) - len({link.order_index for link in links}),
            "platforms": dict(Counter(p.platform for p in problems)),
            "difficulty": dict(Counter(p.difficulty for p in problems)),
            "with_video_links": sum(1 for p in problems if p.video_links),
            "with_hints": sum(1 for p in problems if p.hints),
            "with_article": sum(
                1 for p in problems if (p.extra or {}).get("article_url")
            ),
            "missing_url": sum(1 for p in problems if not p.url),
            "missing_title": sum(1 for p in problems if not p.title),
            "unrated_with_rating_source": sum(
                1 for p in problems if p.rating is None and p.rating_source
            ),
            "by_bucket": {
                str(s.rating_bucket): memberships_by_section[s.slug]
                for s in sections
                if s.rating_bucket
            },
            "provenance": bool(sheet.source_metadata),
            "source_hash": (sheet.source_metadata or {}).get("source_hash"),
        }

    out["problems_total"] = db.scalar(select(func.count()).select_from(Problem))
    out["problems_by_platform"] = dict(
        db.execute(select(Problem.platform, func.count()).group_by(Problem.platform)).all()
    )
    out["problem_topic_rows"] = db.scalar(
        select(func.count()).select_from(ProblemTopic)
    )
    out["canonical_collisions"] = db.scalar(
        select(func.count()).select_from(
            select(Problem.platform, Problem.external_id)
            .group_by(Problem.platform, Problem.external_id)
            .having(func.count() > 1)
            .subquery()
        )
    )
    return out


def report(snapshot: dict, compare: dict | None) -> int:
    checks: list[tuple[str, bool, str]] = []
    sheets = snapshot["sheets"]

    striver = sheets.get("striver-a2z")
    if striver is None:
        checks.append(("striver-a2z present", False, "sheet missing"))
    else:
        print("Striver A2Z — per-step reconciliation")
        print(f"  {'step':<32}{'sheet':>7}{'entries':>9}{'members':>9}{'delta':>7}")
        drift = {}
        for slug, expected in STRIVER_EXPECTED.items():
            entries = striver["entries_by_section"].get(slug, 0)
            members = striver["memberships_by_section"].get(slug, 0)
            if entries != expected:
                drift[slug] = (expected, entries)
            print(f"  {slug:<32}{expected:>7}{entries:>9}{members:>9}{entries - expected:>7}")
        total_members = sum(striver["memberships_by_section"].values())
        print(f"  {'TOTAL':<32}{STRIVER_SOURCE_ROWS:>7}"
              f"{striver['source_entries']:>9}{total_members:>9}")
        print()
        checks += [
            ("striver: 474 source entries preserved",
             striver["source_entries"] == STRIVER_SOURCE_ROWS,
             str(striver["source_entries"])),
            ("striver: 455 canonical memberships",
             striver["memberships"] == STRIVER_CANONICAL, str(striver["memberships"])),
            ("striver: per-step counts match the public page",
             not drift, str(drift)),
            ("striver: 18 sections", striver["sections"] == 18, str(striver["sections"])),
            ("striver: every membership carries its source rows",
             striver["memberships_without_entries"] == 0,
             str(striver["memberships_without_entries"])),
            ("striver: no duplicate memberships",
             striver["duplicate_memberships"] == 0,
             str(striver["duplicate_memberships"])),
            ("striver: no membership missing a URL",
             striver["missing_url"] == 0, str(striver["missing_url"])),
            ("striver: no membership missing a title",
             striver["missing_title"] == 0, str(striver["missing_title"])),
            ("striver: provenance recorded", striver["provenance"], ""),
        ]
        multi = striver["source_entries"] - striver["memberships"]
        checks.append((
            "striver: 19 extra sheet rows kept on collapsed memberships",
            multi == STRIVER_SOURCE_ROWS - STRIVER_CANONICAL, str(multi),
        ))

    cp31 = sheets.get("cp31")
    if cp31 is None:
        checks.append(("cp31 present", False, "sheet missing"))
    else:
        print("CP-31 — rating bucket reconciliation")
        bucket_drift = {}
        for bucket in CP31_BUCKETS:
            got = cp31["by_bucket"].get(str(bucket), 0)
            if got != CP31_PER_BUCKET:
                bucket_drift[bucket] = got
            print(f"  {bucket:<8}{got:>5}  (expected {CP31_PER_BUCKET})")
        print()
        checks += [
            ("cp31: 372 problems", cp31["memberships"] == CP31_PROBLEMS,
             str(cp31["memberships"])),
            ("cp31: 12 rating buckets", len(cp31["by_bucket"]) == len(CP31_BUCKETS),
             str(sorted(cp31["by_bucket"], key=int))),
            ("cp31: 31 problems in every bucket", not bucket_drift, str(bucket_drift)),
            ("cp31: no duplicate memberships", cp31["duplicate_memberships"] == 0,
             str(cp31["duplicate_memberships"])),
            ("cp31: provenance recorded", cp31["provenance"], ""),
        ]

    checks.append((
        "no canonical identity collisions",
        snapshot["canonical_collisions"] == 0, str(snapshot["canonical_collisions"]),
    ))

    if compare is not None:
        print("Idempotency — before vs after re-import")
        drifted: list[str] = []
        for slug, after in sheets.items():
            before = compare["sheets"].get(slug)
            if before is None:
                drifted.append(f"{slug}: new sheet")
                continue
            for key in (
                "memberships", "sections", "source_entries", "with_video_links",
                "with_hints", "with_article", "duplicate_memberships",
            ):
                if before[key] != after[key]:
                    drifted.append(f"{slug}.{key}: {before[key]} -> {after[key]}")
            print(f"  {slug:<16} memberships {before['memberships']} -> {after['memberships']}"
                  f"   entries {before['source_entries']} -> {after['source_entries']}"
                  f"   videos {before['with_video_links']} -> {after['with_video_links']}")
        for key in ("problems_total", "problem_topic_rows"):
            if compare[key] != snapshot[key]:
                drifted.append(f"{key}: {compare[key]} -> {snapshot[key]}")
        print(f"  problems_total   {compare['problems_total']} -> {snapshot['problems_total']}")
        print(f"  problem_topics   {compare['problem_topic_rows']} -> {snapshot['problem_topic_rows']}")
        print()
        checks.append(("re-import changed nothing", not drifted, "; ".join(drifted)))

    print("Checks")
    for label, ok, detail in checks:
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{suffix}")

    failed = [label for label, ok, _ in checks if not ok]
    print()
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Write the raw snapshot here.")
    parser.add_argument("--compare", help="Compare against a previous snapshot.")
    args = parser.parse_args()

    with session_scope() as db:
        snapshot = collect(db)

    if args.json:
        Path(args.json).write_text(json.dumps(snapshot, indent=2, sort_keys=True))

    previous = None
    if args.compare:
        path = Path(args.compare)
        if not path.exists():
            print(f"No snapshot at {path}", file=sys.stderr)
            return 1
        previous = json.loads(path.read_text())

    return report(snapshot, previous)


if __name__ == "__main__":
    raise SystemExit(main())
