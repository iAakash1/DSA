"""Per-user progress: status, submissions, sessions, mistakes, notes, reviews.

Design rule: never collapse history into a boolean. `UserProblem` is a derived
cache over `Submission` + `SolvingSession`; the underlying rows stay forever so
analytics can ask questions we have not thought of yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, JSONType, UTCDateTime
from app.models.enums import ProblemStatus

if TYPE_CHECKING:
    from app.models.problem import Problem


class UserProblem(UUIDPrimaryKey, Timestamps, Base):
    """Denormalized per-user state for one problem."""

    __tablename__ = "user_problems"
    __table_args__ = (
        UniqueConstraint("user_id", "problem_id", name="uq_user_problems_user_problem"),
        Index("ix_user_problems_user_status", "user_id", "status"),
        Index("ix_user_problems_review_due", "user_id", "review_due_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(16), default=ProblemStatus.UNSOLVED, nullable=False
    )
    first_solved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_solved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_attempted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    solved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Strongest (most independent) solution source achieved so far.
    best_solution_source: Mapped[str | None] = mapped_column(String(16))
    #: 1-5 self-reported.
    confidence: Mapped[int | None] = mapped_column(Integer)
    total_time_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    review_interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    problem: Mapped["Problem"] = relationship()

    @property
    def is_solved(self) -> bool:
        return self.status in (
            ProblemStatus.SOLVED,
            ProblemStatus.MASTERED,
            ProblemStatus.REVISIT,
        )


class Submission(UUIDPrimaryKey, Timestamps, Base):
    """One submission. Synced from a platform or recorded manually."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "platform",
            "external_submission_id",
            name="uq_submissions_user_platform_external",
        ),
        Index("ix_submissions_user_submitted", "user_id", "submitted_at"),
        Index("ix_submissions_user_problem", "user_id", "problem_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Null for manual entries; unique per user+platform when present, which is
    #: what makes re-running a sync idempotent.
    external_submission_id: Mapped[str | None] = mapped_column(String(64))

    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(64))
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16), default="sync", nullable=False)
    #: Platform contest this submission belongs to, when known.
    external_contest_id: Mapped[str | None] = mapped_column(String(64))
    #: True when submitted during the live contest window.
    during_contest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    problem: Mapped["Problem"] = relationship()


class SolvingSession(UUIDPrimaryKey, Timestamps, Base):
    """A deliberate attempt at a problem, with the metadata that makes
    analytics meaningful: time, independence, confidence, perception."""

    __tablename__ = "solving_sessions"
    __table_args__ = (
        Index("ix_solving_sessions_user_finished", "user_id", "finished_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )

    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    result: Mapped[str] = mapped_column(String(16), default="solved", nullable=False)
    solution_source: Mapped[str] = mapped_column(
        String(16), default="independent", nullable=False
    )
    #: 1-5, how hard it felt regardless of official rating.
    difficulty_perception: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[int | None] = mapped_column(Integer)
    approach: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    problem: Mapped["Problem"] = relationship()


class Mistake(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "mistakes"
    __table_args__ = (Index("ix_mistakes_user_type", "user_id", "mistake_type"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("solving_sessions.id", ondelete="SET NULL")
    )
    mistake_type: Mapped[str] = mapped_column(String(48), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    problem: Mapped["Problem"] = relationship()


class ProblemNote(UUIDPrimaryKey, Timestamps, Base):
    """Markdown notes. Append-only by design — a new note never silently
    overwrites an old one."""

    __tablename__ = "problem_notes"
    __table_args__ = (Index("ix_problem_notes_user_problem", "user_id", "problem_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), default="insight", nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)

    problem: Mapped["Problem"] = relationship()


class Review(UUIDPrimaryKey, Timestamps, Base):
    """Spaced-repetition entry for a problem."""

    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_user_scheduled", "user_id", "scheduled_for", "completed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: Outcome of the review: recalled | partial | forgotten
    outcome: Mapped[str | None] = mapped_column(String(16))
    evidence: Mapped[dict | None] = mapped_column(JSONType)

    problem: Mapped["Problem"] = relationship()
