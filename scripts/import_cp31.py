#!/usr/bin/env python3
"""Import the CP-31 sheet.

    python scripts/import_cp31.py                       # bundled seed file
    python scripts/import_cp31.py path/to/cp31.json     # your own export
    python scripts/import_cp31.py --offline             # no Codeforces lookup

Ratings and titles come from the Codeforces problemset API, and each problem is
placed in the rating bucket that matches its authoritative rating — so the file
only has to list problem ids.
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

DEFAULT_PATH = REPO_ROOT / "data" / "seed" / "cp31.json"


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
        source_path = Path(args.source or args.path or DEFAULT_PATH).resolve()
        raw = load_import_file(source_path)

        # RAW -> NORMALIZED -> DATABASE. The raw export is never rewritten, so
        # the whole corpus stays rebuildable from it if the database is lost.
        raw_dir = REPO_ROOT / "data" / "sources" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_copy = raw_dir / "cp31.json"
        if source_path.resolve() != raw_copy.resolve():
            shutil.copy2(source_path, raw_copy)

        payload = adapt_payload(raw, slug="cp31", name="CP-31", kind="cp31")

        norm_dir = REPO_ROOT / "data" / "sources" / "normalized"
        norm_dir.mkdir(parents=True, exist_ok=True)
        (norm_dir / "cp31.normalized.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        provenance = {
            "source_name": "CP-31 (TLE Eliminators)",
            "source_url": _rel(source_path),
            "source_hash": source_fingerprint(raw),
            "raw_path": _rel(raw_copy),
        }
        with session_scope() as db:
            report = import_sheet(
                db, payload, enrich=not args.offline, provenance=provenance,
                reconcile=args.reconcile
            )
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    print(report.summary())
    print(f"  raw source:  {provenance['raw_path']}")
    print(f"  normalized:  data/sources/normalized/{'cp31'}.normalized.json")
    print(f"  source hash: {provenance['source_hash'][:16]}…")
    for warning in report.warnings:
        print(f"  warning: {warning}")
    for error in report.errors:
        print(f"  error:   {error}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
