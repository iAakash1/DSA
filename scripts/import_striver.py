#!/usr/bin/env python3
"""Import Striver's A2Z sheet.

    python scripts/import_striver.py                 # reconstructed corpus
    python scripts/import_striver.py --reconcile      # source is authoritative
    python scripts/import_striver.py path/to/striver.json

Run `scripts/build_striver_a2z.py` first to (re)build the corpus from
takeUforward's public sheet page. Problem titles, difficulty and topic tags are
fetched from LeetCode when reachable; the values in the file are the fallback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from app.core.config import REPO_ROOT
from app.core.errors import AppError
from app.db.session import session_scope
import json
import shutil

from app.services.import_service import (
    adapt_payload,
    import_sheet,
    load_import_file,
    source_fingerprint,
)

#: The reconstructed 474-row corpus. Falls back to the small development seed
#: only if the reconstruction has never been run.
DEFAULT_PATH = REPO_ROOT / "data" / "sources" / "striver_a2z.json"
SEED_PATH = REPO_ROOT / "data" / "seed" / "striver_a2z.json"


def _rel(path: Path) -> str:
    """Repo-relative path where possible, absolute otherwise."""
    try:
        return str(path.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=None)
    parser.add_argument("--source", dest="source", help="Path to an authoritative export.")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--reconcile", action="store_true",
                        help="Treat the source as the complete corpus; drop stale memberships.")
    args = parser.parse_args()

    try:
        chosen = args.source or args.path
        if chosen is None:
            chosen = DEFAULT_PATH if DEFAULT_PATH.exists() else SEED_PATH
            if chosen is SEED_PATH:
                print(
                    "Using the development seed — run scripts/build_striver_a2z.py "
                    "for the complete corpus.",
                    file=sys.stderr,
                )
        source_path = Path(chosen).resolve()
        raw = load_import_file(source_path)

        # RAW -> NORMALIZED -> DATABASE. The raw export is never rewritten, so
        # the whole corpus stays rebuildable from it if the database is lost.
        raw_dir = REPO_ROOT / "data" / "sources" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_copy = raw_dir / "striver-a2z.json"
        if source_path.resolve() != raw_copy.resolve():
            shutil.copy2(source_path, raw_copy)

        payload = adapt_payload(raw, slug="striver-a2z", name="Striver A2Z", kind="a2z")

        norm_dir = REPO_ROOT / "data" / "sources" / "normalized"
        norm_dir.mkdir(parents=True, exist_ok=True)
        (norm_dir / "striver-a2z.normalized.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        provenance = {
            "source_name": "Striver A2Z (takeUforward)",
            "source_url": _rel(source_path),
            "source_hash": source_fingerprint(raw),
            "raw_path": _rel(raw_copy),
            # The builder records where the corpus came from and what it
            # verified; keep that with the sheet rather than restating it.
            **({"reconstruction": raw["_provenance"]} if isinstance(raw, dict)
               and "_provenance" in raw else {}),
        }
        with session_scope() as db:
            report = import_sheet(
                db, payload, enrich=not args.offline, provenance=provenance,
                reconcile=args.reconcile,
            )
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    print(report.summary())
    print(f"  raw source:  {provenance['raw_path']}")
    print(f"  normalized:  data/sources/normalized/{'striver-a2z'}.normalized.json")
    print(f"  source hash: {provenance['source_hash'][:16]}…")
    for warning in report.warnings:
        print(f"  warning: {warning}")
    for error in report.errors:
        print(f"  error:   {error}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
