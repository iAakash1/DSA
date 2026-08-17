#!/usr/bin/env python3
"""Emit `supabase/migrations/*.sql` from the Alembic chain.

There is exactly one source of truth for schema — the Alembic revisions — and
this script renders them as plain PostgreSQL DDL so the Supabase CLI
(`supabase db push`, `supabase migration list`) can manage them natively.

Because the SQL is generated rather than hand-written, the two can never drift.
Do not edit files in supabase/migrations by hand: add an Alembic revision and
re-run this script.

Usage:
    python scripts/generate_supabase_migrations.py
    python scripts/generate_supabase_migrations.py --check   # CI: fail if stale
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
OUTPUT_DIR = REPO_ROOT / "supabase" / "migrations"

sys.path.insert(0, str(BACKEND))

HEADER = """-- ---------------------------------------------------------------------------
-- GENERATED FILE — DO NOT EDIT BY HAND.
--
-- Produced by: python scripts/generate_supabase_migrations.py
-- Source:      backend/alembic/versions/{source}
--
-- To change the schema: add an Alembic revision in backend/alembic/versions,
-- then re-run the generator. Editing this file directly will be overwritten
-- and will desynchronise the ORM models from the database.
-- ---------------------------------------------------------------------------

"""


def _revisions() -> list[tuple[str, str, str]]:
    """(revision, down_revision, filename) ordered oldest-first."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)

    ordered = list(script.walk_revisions("base", "heads"))
    ordered.reverse()
    return [
        (rev.revision, rev.down_revision or "base", Path(rev.path).name)
        for rev in ordered
    ]


def _render(from_rev: str, to_rev: str) -> str:
    """Render one migration step as SQL, targeting PostgreSQL."""
    # Offline mode ("--sql") emits DDL without touching a database. The URL only
    # selects the dialect, so a placeholder host is fine and nothing connects.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND / "alembic.ini"),
            "upgrade",
            "--sql",
            f"{from_rev}:{to_rev}",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=_postgres_env(),
    )
    if result.returncode != 0:
        raise SystemExit(
            f"alembic failed rendering {from_rev}:{to_rev}\n{result.stderr}"
        )
    return _clean(result.stdout)


def _postgres_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    # Force the Postgres dialect regardless of the developer's local .env.
    env["DATABASE_URL"] = "postgresql+psycopg://generator@localhost:5432/cp_forge"
    return env


def _clean(sql: str) -> str:
    """Strip Alembic's transaction wrappers and version bookkeeping noise.

    The Supabase CLI wraps each migration in its own transaction, and it
    maintains its own migration ledger, so BEGIN/COMMIT here would nest and the
    alembic_version writes would be redundant. Both are preserved in the
    Alembic path; this output is for the Supabase CLI.
    """
    lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.upper() in ("BEGIN;", "COMMIT;"):
            continue
        if re.match(r"^--\s*Running upgrade", stripped):
            lines.append(f"-- {stripped.lstrip('- ')}")
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + "\n"


def generate() -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for index, (revision, down_revision, filename) in enumerate(_revisions(), start=1):
        sql = _render(down_revision, revision)
        # Supabase orders migrations lexicographically by filename prefix.
        slug = re.sub(r"^[0-9a-f]+_", "", filename).removesuffix(".py")
        target = OUTPUT_DIR / f"{index:04d}_{slug}.sql"
        target.write_text(HEADER.format(source=filename) + sql, encoding="utf-8")
        written.append(target)
        print(f"  {target.relative_to(REPO_ROOT)}  ({len(sql.splitlines())} lines)")

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed SQL differs from the chain.",
    )
    args = parser.parse_args()

    if args.check:
        existing = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(OUTPUT_DIR.glob("*.sql"))
        }
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            generate()
        regenerated = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(OUTPUT_DIR.glob("*.sql"))
        }
        if existing != regenerated:
            print(
                "supabase/migrations is out of date — run "
                "python scripts/generate_supabase_migrations.py",
                file=sys.stderr,
            )
            return 1
        print("supabase/migrations is up to date")
        return 0

    print("Generating Supabase migrations from the Alembic chain:")
    generate()
    print("\nApply them with either:")
    print("  supabase db push                       # Supabase CLI")
    print("  cd backend && alembic upgrade head     # direct connection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
