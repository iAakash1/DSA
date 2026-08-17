"""Schema verification at startup.

CP-Forge never creates tables from application code. Schema is owned entirely
by the migration chain, so what runs locally is exactly what runs on Supabase.

At startup we only *verify*: is the database reachable, and is the migration
chain at head? A mismatch produces a loud, actionable error rather than a
mystery failure three requests later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import engine

log = get_logger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@dataclass
class SchemaStatus:
    reachable: bool
    current_revision: str | None
    head_revision: str | None
    up_to_date: bool
    error: str | None = None

    @property
    def needs_migration(self) -> bool:
        return self.reachable and not self.up_to_date

    def as_dict(self) -> dict:
        return {
            "reachable": self.reachable,
            "current_revision": self.current_revision,
            "head_revision": self.head_revision,
            "up_to_date": self.up_to_date,
            "error": self.error,
        }


def head_revision() -> str | None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def current_revision(db_engine: Engine | None = None) -> str | None:
    db_engine = db_engine or engine
    inspector = inspect(db_engine)
    if "alembic_version" not in inspector.get_table_names():
        return None
    with db_engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar()


def check_schema(db_engine: Engine | None = None) -> SchemaStatus:
    db_engine = db_engine or engine
    try:
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - report, never raise at startup
        return SchemaStatus(
            reachable=False,
            current_revision=None,
            head_revision=None,
            up_to_date=False,
            error=str(exc),
        )

    try:
        head = head_revision()
        current = current_revision(db_engine)
    except Exception as exc:  # noqa: BLE001
        return SchemaStatus(
            reachable=True,
            current_revision=None,
            head_revision=None,
            up_to_date=False,
            error=str(exc),
        )

    return SchemaStatus(
        reachable=True,
        current_revision=current,
        head_revision=head,
        up_to_date=current is not None and current == head,
    )


def verify_or_warn() -> SchemaStatus:
    """Startup check. Logs actionable guidance; does not create anything."""
    status = check_schema()

    if not status.reachable:
        log.error(
            "database unreachable — check DATABASE_URL",
            error=status.error,
            hint=(
                "For Supabase use the URI from Project Settings > Database and "
                "change the scheme to postgresql+psycopg://"
            ),
        )
        return status

    if status.current_revision is None:
        log.error(
            "database has no schema — migrations have never been applied",
            hint="cd backend && alembic upgrade head",
        )
    elif not status.up_to_date:
        log.error(
            "database schema is out of date",
            current=status.current_revision,
            expected=status.head_revision,
            hint="cd backend && alembic upgrade head",
        )
    else:
        log.info(
            "schema verified",
            revision=status.current_revision,
            dialect="postgresql" if settings.is_postgres else "sqlite",
        )
    return status
