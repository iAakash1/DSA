"""ICPC preparation: roadmap progress, virtual contests, template study.

Readiness is computed from these rows plus the existing solve history. Nothing
here stores a score — scores are derived, so they can never drift from the
activity that justifies them, and "not enough data" stays an honest answer
rather than a zero.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

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
from app.db.types import GUID, DateType, JSONType, UTCDateTime


class ICPCSettings(Timestamps, Base):
    """Per-user ICPC configuration. Absent until the user opts in."""

    __tablename__ = "icpc_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    #: Null until configured — the dashboard then asks for it rather than
    #: inventing a countdown.
    target_date: Mapped[date | None] = mapped_column(DateType)
    team_name: Mapped[str | None] = mapped_column(String(128))
    #: Practice days per week the user can realistically commit to.
    weekly_practice_days: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    #: Codeforces rating the user is aiming to be comfortable at. Null means
    #: readiness falls back to a stated default and says so, rather than
    #: measuring progress against a target the user never chose.
    target_rating: Mapped[int | None] = mapped_column(Integer)
    #: Roadmap node keys the user wants prioritised.
    focus_topics: Mapped[list | None] = mapped_column(JSONType)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ICPCTopicProgress(UUIDPrimaryKey, Timestamps, Base):
    """Self-reported study state for one roadmap topic.

    Solve counts come from the canonical activity tables; this records the
    parts only the user knows — whether they have studied the theory and
    revised the template.
    """

    __tablename__ = "icpc_topic_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_key", name="uq_icpc_topic_progress_user_topic"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Roadmap node key, e.g. "graphs.dijkstra".
    topic_key: Mapped[str] = mapped_column(String(128), nullable=False)
    studied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    last_practiced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notes: Mapped[str | None] = mapped_column(Text)


class TemplateReview(UUIDPrimaryKey, Timestamps, Base):
    """A recorded pass over one C++ template.

    Implementation readiness is measured from these: knowing Dijkstra and being
    able to type it correctly under time pressure are different skills.
    """

    __tablename__ = "template_reviews"
    __table_args__ = (Index("ix_template_reviews_user_slug", "user_id", "template_slug"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    template_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: Did the user write it from memory, or read it?
    from_memory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seconds_taken: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[int | None] = mapped_column(Integer)


class VirtualContest(UUIDPrimaryKey, Timestamps, Base):
    """A timed self-run contest."""

    __tablename__ = "virtual_contests"
    __table_args__ = (Index("ix_virtual_contests_user_started", "user_id", "started_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: draft | running | finished | abandoned
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    penalty_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    problems: Mapped[list["VirtualContestProblem"]] = relationship(
        back_populates="contest",
        cascade="all, delete-orphan",
        order_by="VirtualContestProblem.position",
    )


class VirtualContestProblem(UUIDPrimaryKey, Timestamps, Base):
    """One problem within a virtual contest, with its live outcome."""

    __tablename__ = "virtual_contest_problems"
    __table_args__ = (
        UniqueConstraint(
            "contest_id", "problem_id", name="uq_virtual_contest_problems_contest_problem"
        ),
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("virtual_contests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    label: Mapped[str | None] = mapped_column(String(8))

    #: not_attempted | attempted | solved | upsolved
    status: Mapped[str] = mapped_column(String(16), default="not_attempted", nullable=False)
    wrong_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Minutes from contest start to the accepted solution.
    solved_at_minute: Mapped[int | None] = mapped_column(Integer)
    upsolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    contest: Mapped[VirtualContest] = relationship(back_populates="problems")
    problem: Mapped["object"] = relationship("Problem")


class PracticeSession(UUIDPrimaryKey, Timestamps, Base):
    """A focused practice block: N problems, one topic, a difficulty band."""

    __tablename__ = "practice_sessions"
    __table_args__ = (Index("ix_practice_sessions_user_started", "user_id", "started_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_problems: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    focus_topic: Mapped[str | None] = mapped_column(String(128))
    min_rating: Mapped[int | None] = mapped_column(Integer)
    max_rating: Mapped[int | None] = mapped_column(Integer)

    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: running | finished | abandoned
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)

    problems_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problems_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Problem ids selected for the session, in order.
    problem_ids: Mapped[list | None] = mapped_column(JSONType)
    summary: Mapped[dict | None] = mapped_column(JSONType)


class HintReveal(UUIDPrimaryKey, Timestamps, Base):
    """Records that a user revealed a hint.

    Tracked so hint dependence can inform recommendations and review
    scheduling. It is a signal, never a penalty — the XP for the solve is
    unaffected.
    """

    __tablename__ = "hint_reveals"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "problem_id", "hint_index", name="uq_hint_reveals_user_problem_index"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hint_index: Mapped[int] = mapped_column(Integer, nullable=False)
    revealed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: Session it happened in, when revealed during practice.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("practice_sessions.id", ondelete="SET NULL")
    )


class ReadinessSnapshot(UUIDPrimaryKey, Timestamps, Base):
    """A point-in-time readiness computation, kept for trend lines.

    Components are stored alongside their evidence so a score can always be
    explained, and `has_sufficient_data` records whether it was computable at
    all rather than defaulting to zero.
    """

    __tablename__ = "readiness_snapshots"
    __table_args__ = (Index("ix_readiness_snapshots_user_taken", "user_id", "taken_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    overall: Mapped[float | None] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONType, nullable=False)
    has_sufficient_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
