"""User identity, settings and connected platform accounts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings as app_settings
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, JSONType, UTCDateTime


class Profile(UUIDPrimaryKey, Timestamps, Base):
    """One row per user.

    `id` is the internal identity every other table foreign-keys to. Under
    Clerk it is derived deterministically from the Clerk subject (UUIDv5), and
    under legacy Supabase Auth it mirrors `auth.users.id` — either way it is
    always computed from a verified token, never from request input.
    """

    __tablename__ = "profiles"

    #: The Clerk subject this profile belongs to.
    #:
    #: The internal `id` is already derivable from it, so this column is not
    #: load-bearing for lookups — it exists so the mapping is inspectable in
    #: the database, and unique so one Clerk user can never end up owning two
    #: profiles.
    clerk_user_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(
        String(64),
        default=app_settings.default_timezone,
        server_default=text("'UTC'"),
        nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(Text)

    settings: Mapped["UserSettings"] = relationship(
        back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    platform_accounts: Mapped[list["PlatformAccount"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class UserSettings(Timestamps, Base):
    """Per-user configuration.

    XP rules, level thresholds and streak rules live here as JSON overrides so
    they are configurable without a migration. `None` means "use the default
    ruleset" from `app.gamification.rules`.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )

    daily_goal: Mapped[int] = mapped_column(
        Integer,
        default=app_settings.default_daily_goal,
        server_default=text("2"),
        nullable=False,
    )
    weekly_goal: Mapped[int] = mapped_column(
        Integer, default=14, server_default=text("14"), nullable=False
    )

    max_freezes: Mapped[int] = mapped_column(
        Integer, default=3, server_default=text("3"), nullable=False
    )
    freeze_cost_xp: Mapped[int] = mapped_column(
        Integer, default=500, server_default=text("500"), nullable=False
    )
    auto_apply_freeze: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    xp_rules_override: Mapped[dict | None] = mapped_column(JSONType)
    level_config_override: Mapped[list | None] = mapped_column(JSONType)
    streak_qualifying_activities: Mapped[list | None] = mapped_column(JSONType)

    ai_daily_insights: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    ai_weekly_reviews: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    ai_contest_analysis: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    ai_recommendations: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    ai_coach: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    ai_daily_request_budget: Mapped[int] = mapped_column(
        Integer,
        default=app_settings.ai_requests_per_day,
        server_default=text("50"),
        nullable=False,
    )
    ai_model_override: Mapped[str | None] = mapped_column(String(128))

    profile: Mapped[Profile] = relationship(back_populates="settings")


class PlatformAccount(UUIDPrimaryKey, Timestamps, Base):
    """A connected LeetCode / Codeforces account."""

    __tablename__ = "platform_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_platform_accounts_user_platform"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    connected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_sync_status: Mapped[str | None] = mapped_column(String(32))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    #: Opaque per-integration cursor (e.g. highest submission id already seen).
    sync_cursor: Mapped[dict | None] = mapped_column(JSONType)

    #: Platform-reported rating snapshot, refreshed on sync.
    current_rating: Mapped[int | None] = mapped_column(Integer)
    max_rating: Mapped[int | None] = mapped_column(Integer)

    profile: Mapped[Profile] = relationship(back_populates="platform_accounts")
