"""Declarative base and shared mixins."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import GUID, UTCDateTime

# Explicit naming so Alembic autogenerate produces stable, diffable migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: Server-side defaults matter here beyond convenience: Supabase permits direct
#: client writes and database triggers, neither of which run SQLAlchemy's
#: Python-side defaults. Every NOT NULL column with a default therefore carries
#: a real DDL DEFAULT so the schema is valid on its own.
#:
#: UUID primary keys are the exception: `gen_random_uuid()` is Postgres-only and
#: would be invalid DDL on SQLite, so that default is applied in the
#: Postgres-only migration instead of here.


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
