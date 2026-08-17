"""Deterministic recommendations.

The recommendation engine — not the LLM — decides *which* problems to suggest.
Every row carries machine-readable evidence so the UI (and optionally the AI)
can explain the choice without inventing a rationale.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, JSONType, UTCDateTime

if TYPE_CHECKING:
    from app.models.problem import Problem


class Recommendation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "problem_id", "batch_id", name="uq_recommendations_user_problem_batch"
        ),
        Index("ix_recommendations_user_generated", "user_id", "generated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)

    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    #: weak_topic | weak_pattern | cp31_progression | striver_progression |
    #: review | difficulty_step | neglected_topic | collection
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Structured facts behind the recommendation (mastery, success rate,
    #: days since practice ...). Never fabricated.
    evidence: Mapped[dict | None] = mapped_column(JSONType)

    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    problem: Mapped["Problem"] = relationship()


class SyncRun(UUIDPrimaryKey, Timestamps, Base):
    """Audit trail for every external sync attempt.

    Powers honest error messages ("last successful sync: ...") instead of a
    bare 500 when Codeforces is down.
    """

    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_user_platform", "user_id", "platform", "started_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    submissions_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submissions_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONType)
