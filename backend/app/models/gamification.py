"""XP ledger, streaks, freezes, activity days, achievements, goals, missions.

Two rules shape this module:

1. XP is an append-only ledger with a unique `dedupe_key`. Balances are derived,
   never edited. Re-solving a problem or re-running a sync cannot double-award.
2. Activity is keyed by a calendar date *already resolved in the user's
   timezone*. Nothing here reasons about UTC dates.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, DateType, JSONType, UTCDateTime


class UserStats(Timestamps, Base):
    """Denormalized totals. Always rebuildable from the ledger + activity."""

    __tablename__ = "user_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    total_xp: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    level: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    current_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_active_date: Mapped[date | None] = mapped_column(DateType)
    available_freezes: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    problems_solved: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    independent_solves: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_recomputed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ActivityDay(UUIDPrimaryKey, Timestamps, Base):
    """One row per active calendar day, in the user's timezone."""

    __tablename__ = "activity_days"
    __table_args__ = (
        UniqueConstraint("user_id", "activity_date", name="uq_activity_days_user_date"),
        Index("ix_activity_days_user_date", "user_id", "activity_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    activity_date: Mapped[date] = mapped_column(DateType, nullable=False)

    problems_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minutes_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submissions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upsolves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviews_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: True when a freeze was consumed to protect this (otherwise empty) day.
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    topics_touched: Mapped[list | None] = mapped_column(JSONType)


class XPTransaction(UUIDPrimaryKey, Timestamps, Base):
    """Append-only XP ledger.

    `dedupe_key` is the whole anti-exploit mechanism: every award computes a
    deterministic key (e.g. `first_solve:<problem_id>`), and the unique index
    makes a second award physically impossible.
    """

    __tablename__ = "xp_transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_xp_transactions_user_dedupe"),
        Index("ix_xp_transactions_user_date", "user_id", "activity_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    problem_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="SET NULL")
    )
    activity_date: Mapped[date] = mapped_column(DateType, nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class StreakFreezeTransaction(UUIDPrimaryKey, Timestamps, Base):
    """Every freeze movement is recorded. History is never rewritten silently."""

    __tablename__ = "streak_freeze_transactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "dedupe_key", name="uq_streak_freeze_transactions_user_dedupe"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    xp_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: For `used`: the day the freeze protected.
    applies_to_date: Mapped[date | None] = mapped_column(DateType)
    balance_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class Achievement(UUIDPrimaryKey, Timestamps, Base):
    """Data-driven achievement definition.

    `criteria` is evaluated by `app.gamification.achievements`, so adding a new
    achievement is a seed-data change, not a code change.
    """

    __tablename__ = "achievements"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    icon: Mapped[str | None] = mapped_column(String(32))
    tier: Mapped[str] = mapped_column(String(16), default="bronze", nullable=False)
    criteria: Mapped[dict] = mapped_column(JSONType, nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserAchievement(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "achievement_id", name="uq_user_achievements_user_achievement"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("achievements.id", ondelete="CASCADE"), index=True, nullable=False
    )
    unlocked_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: 0.0-1.0 toward unlocking; 1.0 once unlocked.
    progress: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    achievement: Mapped[Achievement] = relationship()


class DailyGoal(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "daily_goals"
    __table_args__ = (
        UniqueConstraint("user_id", "goal_date", name="uq_daily_goals_user_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal_date: Mapped[date] = mapped_column(DateType, nullable=False)
    target: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WeeklyGoal(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "weekly_goals"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", "kind", name="uq_weekly_goals_user_week_kind"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    week_start: Mapped[date] = mapped_column(DateType, nullable=False)
    #: problems | cp31 | topic | rating | contests | upsolves | reviews
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSONType)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class DailyMission(UUIDPrimaryKey, Timestamps, Base):
    """Generated from real user data — never random filler."""

    __tablename__ = "daily_missions"
    __table_args__ = (
        UniqueConstraint("user_id", "mission_date", "code", name="uq_daily_missions_user_date_code"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mission_date: Mapped[date] = mapped_column(DateType, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: Constraints used to evaluate progress (topic slug, min rating, sheet...).
    params: Mapped[dict | None] = mapped_column(JSONType)
