"""Test fixtures.

Every test runs against a throwaway SQLite database created from the real
migration chain — not `create_all` — so the tests exercise the same schema that
ships to Supabase.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Point the app at a temp database before anything imports settings.
_TMP_DIR = tempfile.mkdtemp(prefix="cp-forge-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"
os.environ["ALLOW_SQLITE"] = "true"  # tests run on SQLite for speed
os.environ["AUTH_MODE"] = "local"
os.environ["GROQ_API_KEY"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["CODEFORCES_HANDLE"] = ""
os.environ["LEETCODE_USERNAME"] = ""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import AuthenticatedUser  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.gamification.achievements import seed_achievements  # noqa: E402
from app.models.enums import Platform  # noqa: E402
from app.services.problem_service import get_or_create_problem  # noqa: E402
from app.services.taxonomy import seed_taxonomy  # noqa: E402
from app.services.user_service import ensure_profile  # noqa: E402
from app.utils.normalize import ProblemRef  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Apply the real migration chain once per test session."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def user(db: Session):
    """A fresh profile per test, so tests never share XP or streak state."""
    identity = AuthenticatedUser(
        id=uuid.uuid4(), email="test@example.com", username="tester", claims={}
    )
    return ensure_profile(db, identity)


@pytest.fixture
def second_user(db: Session):
    identity = AuthenticatedUser(
        id=uuid.uuid4(), email="other@example.com", username="other", claims={}
    )
    return ensure_profile(db, identity)


@pytest.fixture(scope="session")
def taxonomy(migrated_database):
    session = SessionLocal()
    try:
        seed_taxonomy(session)
        seed_achievements(session)
    finally:
        session.close()


@pytest.fixture
def make_problem(db: Session):
    """Factory for canonical problems."""

    def _make(
        external_id: str = "1400B",
        platform: str = Platform.CODEFORCES,
        rating: int | None = 1200,
        difficulty: str = "medium",
        title: str | None = None,
        tags: list[str] | None = None,
    ):
        ref = ProblemRef(
            platform=platform,
            external_id=external_id,
            slug=external_id,
            contest_id=1400 if platform == Platform.CODEFORCES else None,
            index="B" if platform == Platform.CODEFORCES else None,
        )
        problem, _ = get_or_create_problem(
            db,
            ref,
            title=title or f"Problem {external_id}",
            rating=rating,
            difficulty=difficulty,
            tags=tags,
        )
        return problem

    return _make
