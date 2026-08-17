#!/usr/bin/env python3
"""Reconstruct the complete Striver A2Z corpus from takeUforward's own page.

    python scripts/build_striver_a2z.py            # fetch the live sheet
    python scripts/build_striver_a2z.py --offline  # rebuild from the stored raw copy

The A2Z sheet page ships its full corpus as structured data inside the React
Server Component payload — 18 steps, their sub-steps, and every problem with
its difficulty, article, YouTube lecture and (where one exists) LeetCode link.
Nothing here logs in, bypasses a paywall or scrapes a protected endpoint: it
reads the same public page a browser renders, and the numbers it produces are
checked against the totals the page itself prints.

RAW -> NORMALIZED -> VALIDATED. The raw extraction is written verbatim so the
corpus stays rebuildable without another fetch, and every count is verified
before anything is emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import _bootstrap  # noqa: F401

from app.core.config import REPO_ROOT

SHEET_URL = (
    "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2"
)

RAW_HTML = REPO_ROOT / "data" / "sources" / "raw" / "striver_a2z.page.html"
RAW_JSON = REPO_ROOT / "data" / "sources" / "raw" / "striver_a2z.raw.json"
OUT_JSON = REPO_ROOT / "data" / "sources" / "striver_a2z.json"
NORM_JSON = REPO_ROOT / "data" / "sources" / "normalized" / "striver_a2z.normalized.json"

#: The 18 steps, keyed by the category id the sheet publishes. Keying on the id
#: rather than the display name means a wording change upstream is detected as
#: a *name* change, not silently mistaken for a new step. An id that is not in
#: this table aborts the build rather than being guessed at.
STEPS: dict[str, tuple[str, str | None]] = {
    "683": ("step-01-basics", "basics"),
    "681": ("step-02-sorting", "sorting"),
    "686": ("step-03-arrays", "arrays"),
    "673": ("step-04-binary-search", "binary-search"),
    "689": ("step-05-strings", "strings"),
    "682": ("step-06-linked-list", "linked-list"),
    "684": ("step-07-recursion", "recursion"),
    "676": ("step-08-bit-manipulation", "bit-manipulation"),
    "687": ("step-09-stack-queue", "stack-queue"),
    "685": ("step-10-sliding-window", "sliding-window"),
    "680": ("step-11-heaps", "heaps"),
    "679": ("step-12-greedy", "greedy"),
    "675": ("step-13-binary-trees", "binary-tree"),
    "674": ("step-14-bst", "bst"),
    "678": ("step-15-graphs", "graphs"),
    "677": ("step-16-dynamic-programming", "dynamic-programming"),
    "690": ("step-17-tries", "tries"),
    "688": ("step-18-strings-advanced", "strings"),
}

#: Per-step problem counts as the sheet page *displays* them (the "0/54"
#: counters next to each step), read from the rendered page on 2026-08-17.
#: The page computes these in the browser, so they are not in the HTML and
#: cannot be re-derived from the raw file — pinning them here turns "the
#: upstream sheet changed" into a loud failure instead of a silent drift.
EXPECTED_STEP_COUNTS: dict[str, int] = {
    "step-01-basics": 54,
    "step-02-sorting": 7,
    "step-03-arrays": 40,
    "step-04-binary-search": 32,
    "step-05-strings": 15,
    "step-06-linked-list": 31,
    "step-07-recursion": 25,
    "step-08-bit-manipulation": 18,
    "step-09-stack-queue": 30,
    "step-10-sliding-window": 12,
    "step-11-heaps": 17,
    "step-12-greedy": 15,
    "step-13-binary-trees": 38,
    "step-14-bst": 16,
    "step-15-graphs": 53,
    "step-16-dynamic-programming": 55,
    "step-17-tries": 7,
    "step-18-strings-advanced": 9,
}

_LC_SLUG = re.compile(r"leetcode\.com/problems/([a-z0-9\-]+)", re.IGNORECASE)
_LC_LOGIN = re.compile(r"leetcode\.com/accounts/login/?\?[^#]*next=([^&#]+)", re.IGNORECASE)


def _blank(value: object) -> bool:
    """The payload spells absent values as the literal string `$undefined`."""
    return value in (None, "", "$undefined")


def _clean(value: object) -> str | None:
    return None if _blank(value) else str(value).strip()


def fetch_html() -> str:
    request = urllib.request.Request(
        SHEET_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def extract_categories(html: str) -> list[dict]:
    """Pull the step/sub-step/problem tree out of the RSC flight payload."""
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', html
    )
    if not chunks:
        raise SystemExit(
            "No React flight payload found in the page. The sheet page changed "
            "shape — inspect it before trusting any corpus built from it."
        )
    flight = "".join(json.loads('"' + chunk + '"') for chunk in chunks)

    decoder = json.JSONDecoder()
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for match in re.finditer(r'\{"category_id":', flight):
        try:
            value, _ = decoder.raw_decode(flight, match.start())
        except ValueError:
            continue
        if not isinstance(value, dict) or "subcategories" not in value:
            continue
        cid = str(value["category_id"])
        if cid not in by_id:
            by_id[cid] = value
            order.append(cid)
    return [by_id[cid] for cid in order]


def leetcode_slug(url: str) -> str | None:
    login = _LC_LOGIN.search(url)
    if login:
        # Premium problems link through the sign-in page, which carries the
        # real problem path in `next=`. Reading it is URL parsing, not access.
        url = "https://leetcode.com" + unquote(login.group(1))
    match = _LC_SLUG.search(url)
    return match.group(1).lower() if match else None


def build(categories: list[dict]) -> tuple[dict, dict]:
    unknown = [str(c["category_id"]) for c in categories if str(c["category_id"]) not in STEPS]
    if unknown:
        raise SystemExit(
            f"Unmapped step id(s) {unknown}. The sheet gained or renumbered a "
            "step; add it to STEPS deliberately rather than importing a guess."
        )

    sections: list[dict] = []
    problems: list[dict] = []
    stats = {
        "rows": 0,
        "leetcode": 0,
        "takeuforward": 0,
        "with_video": 0,
        "with_article": 0,
        "difficulty": {},
        "per_step": {},
        "unparsed_leetcode": [],
    }

    for order, category in enumerate(categories):
        cid = str(category["category_id"])
        slug, topic = STEPS[cid]
        sections.append(
            {
                "slug": slug,
                "name": str(category["category_name"]).strip(),
                "kind": "topic",
                "topic": topic,
                "order": order,
            }
        )

        step_rows = 0
        for sub in category["subcategories"]:
            sub_name = str(sub["subcategory_name"]).strip()
            for raw in sub["problems"]:
                stats["rows"] += 1
                step_rows += 1
                index = stats["rows"] - 1

                title = str(raw["problem_name"]).strip()
                difficulty = str(raw["difficulty"]).strip().lower()
                stats["difficulty"][difficulty] = stats["difficulty"].get(difficulty, 0) + 1

                article = _clean(raw.get("article"))
                youtube = _clean(raw.get("youtube"))
                plus = _clean(raw.get("plus"))
                editorial = _clean(raw.get("editorial"))
                tuf_slug = plus.rsplit("/", 1)[-1].split("?")[0] if plus else None

                entry: dict = {
                    "title": title,
                    "difficulty": difficulty,
                    "section": slug,
                    "order": index,
                    "label": sub_name,
                    "extra": {
                        "source": "striver-a2z",
                        "tuf_problem_id": str(raw["problem_id"]),
                        "tuf_slug": tuf_slug,
                        "step": str(category["category_name"]).strip(),
                        "sub_step": sub_name,
                        "article_url": article,
                        "editorial_path": editorial,
                    },
                }
                if topic:
                    entry["topics"] = [topic]
                if youtube:
                    entry["video_links"] = [youtube]
                    stats["with_video"] += 1
                if article:
                    stats["with_article"] += 1

                lc_url = _clean(raw.get("leetcode"))
                slug_lc = leetcode_slug(lc_url) if lc_url else None
                if lc_url and not slug_lc:
                    stats["unparsed_leetcode"].append((title, lc_url))
                if slug_lc:
                    entry["platform"] = "leetcode"
                    entry["external_id"] = slug_lc
                    stats["leetcode"] += 1
                else:
                    # takeUforward-native. The numeric sheet id is the identity;
                    # the slug is not, because takeUforward serves different
                    # problems under one slug (`/problems/cpp` is two of them).
                    entry["platform"] = "takeuforward"
                    entry["external_id"] = str(raw["problem_id"])
                    # Not the identity — several problems share a slug — but a
                    # far better search term than the numeric id.
                    if tuf_slug:
                        entry["display_slug"] = tuf_slug
                    entry["problem_url"] = (
                        f"https://takeuforward.org{plus}" if plus else article or SHEET_URL
                    )
                    stats["takeuforward"] += 1

                problems.append(entry)

        stats["per_step"][slug] = step_rows

    payload = {
        "sheet": {
            "slug": "striver-a2z",
            "name": "Striver A2Z DSA",
            "kind": "a2z",
            "description": (
                "takeUforward's A2Z course sheet: 18 steps from language basics "
                "through tries and string algorithms."
            ),
            "source_url": SHEET_URL,
            "order": 0,
        },
        "sections": sections,
        "problems": problems,
    }
    return payload, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Rebuild from the stored raw page instead of fetching it.",
    )
    args = parser.parse_args()

    RAW_HTML.parent.mkdir(parents=True, exist_ok=True)
    NORM_JSON.parent.mkdir(parents=True, exist_ok=True)

    if args.offline:
        if not RAW_HTML.exists():
            print(f"No stored page at {RAW_HTML}; run once without --offline.", file=sys.stderr)
            return 1
        html = RAW_HTML.read_text(encoding="utf-8", errors="replace")
        fetched_at = datetime.fromtimestamp(RAW_HTML.stat().st_mtime, UTC).isoformat()
    else:
        try:
            html = fetch_html()
        except Exception as exc:  # noqa: BLE001 - report, never fall back to a guess
            print(f"Could not fetch the sheet page: {exc}", file=sys.stderr)
            print("Re-run with --offline to rebuild from the stored copy.", file=sys.stderr)
            return 1
        RAW_HTML.write_text(html, encoding="utf-8")
        fetched_at = datetime.now(UTC).isoformat()

    categories = extract_categories(html)
    RAW_JSON.write_text(json.dumps(categories, indent=2) + "\n", encoding="utf-8")

    payload, stats = build(categories)

    # -- validation --------------------------------------------------------
    problems = payload["problems"]
    drift = {
        slug: (EXPECTED_STEP_COUNTS.get(slug), got)
        for slug, got in stats["per_step"].items()
        if EXPECTED_STEP_COUNTS.get(slug) != got
    }
    checks: list[tuple[str, bool, str]] = [
        ("18 steps", len(payload["sections"]) == 18, f"{len(payload['sections'])}"),
        (
            "row count matches sum of steps",
            len(problems) == sum(stats["per_step"].values()),
            f"{len(problems)}",
        ),
        (
            "every row has an identity",
            all(p.get("external_id") for p in problems),
            "ok" if all(p.get("external_id") for p in problems) else "missing ids",
        ),
        (
            "every row has a known section",
            {p["section"] for p in problems} <= {s["slug"] for s in payload["sections"]},
            "ok",
        ),
        (
            "no unparsed LeetCode links",
            not stats["unparsed_leetcode"],
            str(stats["unparsed_leetcode"]),
        ),
        (
            "per-step counts match the counters the page displays",
            not drift,
            "no drift" if not drift else f"expected/got {drift}",
        ),
        (
            f"total matches the displayed total ({sum(EXPECTED_STEP_COUNTS.values())})",
            len(problems) == sum(EXPECTED_STEP_COUNTS.values()),
            str(len(problems)),
        ),
    ]

    print("Striver A2Z — extraction report")
    print(f"  steps:        {len(payload['sections'])}")
    print(f"  rows:         {len(problems)}")
    print(f"  leetcode:     {stats['leetcode']}")
    print(f"  takeuforward: {stats['takeuforward']}")
    print(f"  with video:   {stats['with_video']}")
    print(f"  with article: {stats['with_article']}")
    print(f"  difficulty:   {stats['difficulty']}")
    print()
    for label, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}  ({detail})")

    failed = [label for label, ok, _ in checks if not ok]
    if failed:
        print(f"\nRefusing to write a corpus that failed: {failed}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(
        json.dumps(categories, sort_keys=True).encode("utf-8")
    ).hexdigest()
    payload["_provenance"] = {
        "source_name": "takeUforward — Striver's A2Z DSA Course Sheet",
        "source_url": SHEET_URL,
        "extraction": "structured data embedded in the public sheet page (RSC payload)",
        "fetched_at": fetched_at,
        "source_hash": digest,
        "raw_page": str(RAW_HTML.relative_to(REPO_ROOT)),
        "raw_json": str(RAW_JSON.relative_to(REPO_ROOT)),
        "verified": {
            "steps": len(payload["sections"]),
            "rows": len(problems),
            "difficulty": stats["difficulty"],
            "cross_checked_against": "the totals printed by the sheet page itself",
        },
        "notes": [
            "Rows are the sheet's own entries. A problem listed under two steps "
            "collapses onto one canonical problem at import; the import report "
            "states how many.",
            "takeUforward-native problems are keyed by the numeric sheet id, not "
            "the URL slug, because distinct problems share slugs upstream.",
        ],
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    NORM_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\n  raw page:   {RAW_HTML.relative_to(REPO_ROOT)}")
    print(f"  raw json:   {RAW_JSON.relative_to(REPO_ROOT)}")
    print(f"  corpus:     {OUT_JSON.relative_to(REPO_ROOT)}")
    print(f"  hash:       {digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
