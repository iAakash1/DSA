"""Behaviours that differ between SQLite and PostgreSQL.

The main test suite runs on SQLite for speed, which means an entire class of
bug is invisible to it: code that is correct on SQLite and wrong on the
database that actually ships. These tests run only against a real PostgreSQL
server, and are SKIPPED (never silently passed) without one:

    TEST_DATABASE_URL=postgresql://... pytest tests/test_postgres_dialect.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models.problem import Problem
from app.utils.normalize import ProblemRef

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_URL.startswith(("postgres://", "postgresql://")),
    reason="Set TEST_DATABASE_URL to a PostgreSQL URL to run the dialect suite",
)


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@pytest.fixture(scope="module")
def pg_session():
    engine = create_engine(_normalize(TEST_URL), pool_pre_ping=True)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()


def test_unset_json_columns_are_sql_null_not_json_null(pg_session):
    """Regression: `column.is_(None)` must actually match unset JSON columns.

    SQLAlchemy's JSONB type stores Python `None` as the JSON scalar `null`
    unless `none_as_null=True`. With the default, every "no video links"
    problem held a JSON value, `video_links.is_(None)` matched nothing on
    Postgres, and SQLite — which stores a real NULL — could never reveal it.
    """
    from app.services.problem_service import get_or_create_problem

    external_id = f"dialect-{uuid.uuid4().hex[:12]}"
    problem, _ = get_or_create_problem(
        pg_session,
        ProblemRef(platform="leetcode", external_id=external_id, slug=external_id),
        title="Dialect probe",
        commit=True,
    )
    try:
        assert problem.video_links is None

        found = pg_session.scalar(
            select(Problem).where(
                Problem.external_id == external_id, Problem.video_links.is_(None)
            )
        )
        assert found is not None, "is_(None) did not match an unset JSON column"

        typeof = pg_session.execute(
            select(Problem.video_links).where(Problem.external_id == external_id)
        ).scalar_one()
        assert typeof is None
    finally:
        pg_session.delete(problem)
        pg_session.commit()


def test_no_json_null_scalars_remain_in_any_jsonb_column(pg_session):
    """The whole schema, not just the column that surfaced the bug."""
    # information_schema is the authority on which columns are jsonb.
    rows = pg_session.execute(
        text(
            """
            SELECT c.table_name, c.column_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.data_type = 'jsonb'
              AND t.table_type = 'BASE TABLE'
            """
        )
    ).all()
    assert rows, "no jsonb columns found — the query is wrong, not the schema"

    offenders = []
    for table, column in rows:
        count = pg_session.execute(
            text(
                f'SELECT count(*) FROM public."{table}" '
                f'WHERE jsonb_typeof("{column}") = \'null\''
            )
        ).scalar_one()
        if count:
            offenders.append(f"{table}.{column} ({count} rows)")

    assert not offenders, f"JSON null stored instead of SQL NULL: {offenders}"
