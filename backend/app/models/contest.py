"""Contest tracking, participation and per-problem contest outcomes.

Contests are a separate axis from the problem-sheet taxonomy. CodeChef appears
here as a contest platform only — it is never a CP-31/Striver problem source.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, UTCDateTime

if TYPE_CHECKING:
    from app.models.problem import Problem


class Contest(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "contests"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_contests_platform_external"),
    )

    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    contest_type: Mapped[str | None] = mapped_column(String(32))

    problems: Mapped[list["ContestProblem"]] = relationship(
        back_populates="contest", cascade="all, delete-orphan"
    )


class ContestProblem(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "contest_problems"
    __table_args__ = (
        UniqueConstraint("contest_id", "problem_id", name="uq_contest_problems_contest_problem"),
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("contests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index: Mapped[str | None] = mapped_column(String(8))
    points: Mapped[float | None] = mapped_column(Float)

    contest: Mapped[Contest] = relationship(back_populates="problems")
    problem: Mapped["Problem"] = relationship()


class ContestParticipation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "contest_participations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "contest_id", "is_virtual", name="uq_contest_participations_user_contest"
        ),
        Index("ix_contest_participations_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contest_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("contests.id", ondelete="CASCADE"), index=True, nullable=False
    )

    rank: Mapped[int | None] = mapped_column(Integer)
    rating_before: Mapped[int | None] = mapped_column(Integer)
    rating_after: Mapped[int | None] = mapped_column(Integer)
    rating_change: Mapped[int | None] = mapped_column(Integer)
    problems_solved_live: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_upsolved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty: Mapped[int | None] = mapped_column(Integer)
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    contest: Mapped[Contest] = relationship()


class ContestProblemResult(UUIDPrimaryKey, Timestamps, Base):
    """How a single problem went in a single contest — the basis of upsolve
    tracking."""

    __tablename__ = "contest_problem_results"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "contest_id", "problem_id", name="uq_contest_problem_results_unique"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contest_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("contests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(String(16), default="not_attempted", nullable=False)
    solved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_from_start_seconds: Mapped[int | None] = mapped_column(Integer)

    problem: Mapped["Problem"] = relationship()
    contest: Mapped[Contest] = relationship()
