"""Dialect-portable column types.

Supabase Postgres is the production target, but the test suite runs on SQLite
so it needs no network. These decorators keep a single set of models valid on
both: native UUID/JSONB/TIMESTAMPTZ on Postgres, faithful emulations on SQLite.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import CHAR, Date, DateTime, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


class GUID(TypeDecorator):
    """UUID everywhere: native on Postgres, 36-char string on SQLite."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value: Any, dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class JSONType(TypeDecorator):
    """JSONB on Postgres, JSON-encoded TEXT on SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            # `none_as_null` is not optional here. Without it SQLAlchemy stores
            # Python None as JSON `null`, which is a *value* — so `col.is_(None)`
            # matches nothing on Postgres while matching everything it should on
            # SQLite, and the divergence is invisible to a SQLite test suite.
            return dialect.type_descriptor(JSONB(none_as_null=True))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps(value, default=str)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None


class UTCDateTime(TypeDecorator):
    """Always store UTC; always return tz-aware UTC.

    Streak correctness depends on this. SQLite silently drops tzinfo, which is
    exactly the bug class that makes streaks off by one near midnight.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(DateTime(timezone=True))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class DateType(TypeDecorator):
    """Calendar date (already resolved in the user's timezone)."""

    impl = Date
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

    def process_result_value(self, value: Any, dialect) -> date | None:
        if value is None:
            return None
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value
