#!/usr/bin/env python3
"""Back up the CP-Forge database.

PostgreSQL/Supabase uses `pg_dump`; SQLite uses the online backup API (safe to
run while the app is writing). Your data is yours — this always produces a file
you can restore or migrate elsewhere.

    python scripts/backup_database.py
    python scripts/backup_database.py --out data/backups/before-upgrade.sql
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import _bootstrap  # noqa: F401

from app.core.config import REPO_ROOT, settings

BACKUP_DIR = REPO_ROOT / "data" / "backups"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_sqlite(destination: Path) -> Path:
    source = settings.database_url.split("///", 1)[-1]
    if not Path(source).exists():
        raise SystemExit(f"SQLite database not found at {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # The backup API produces a consistent copy even mid-write, which a plain
    # file copy does not.
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return destination


def backup_postgres(destination: Path) -> Path:
    if shutil.which("pg_dump") is None:
        raise SystemExit(
            "pg_dump not found. Install the PostgreSQL client tools:\n"
            "  macOS:  brew install libpq && brew link --force libpq\n"
            "  Debian: sudo apt install postgresql-client"
        )

    # psycopg's URL scheme is not what pg_dump expects.
    parsed = urlparse(settings.database_url.replace("+psycopg", ""))
    dsn = urlunparse(parsed)

    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["pg_dump", "--no-owner", "--no-privileges", "--format=plain", "--file", str(destination), dsn],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Never echo the DSN — it contains the database password.
        raise SystemExit(f"pg_dump failed:\n{result.stderr.replace(dsn, '<dsn>')}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Destination path.")
    args = parser.parse_args()

    if settings.is_postgres:
        default = BACKUP_DIR / f"cp-forge-{_timestamp()}.sql"
        destination = Path(args.out) if args.out else default
        path = backup_postgres(destination)
    else:
        default = BACKUP_DIR / f"cp-forge-{_timestamp()}.db"
        destination = Path(args.out) if args.out else default
        path = backup_sqlite(destination)

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"Backup written: {path.relative_to(REPO_ROOT)}  ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            raise SystemExit(1) from None
        raise
