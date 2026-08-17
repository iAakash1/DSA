"""Editorial / video resources attached to problems.

Video discovery is API-driven and restricted to trusted channels. Candidates
are scored, never blindly picked by view count, and the user can always
override the selection manually.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, JSONType, UTCDateTime


class Resource(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("problem_id", "url", name="uq_resources_problem_url"),
    )

    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Null for globally-discovered resources; set for user-added ones.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(16), default="video", nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)

    external_id: Mapped[str | None] = mapped_column(String(64))
    channel_id: Mapped[str | None] = mapped_column(String(64), index=True)
    channel_title: Mapped[str | None] = mapped_column(String(255))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)

    #: Relevance score from the ranking function; explains why it was chosen.
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONType)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TrustedChannel(UUIDPrimaryKey, Timestamps, Base):
    """A channel whose editorials we trust. `user_id` null = global default."""

    __tablename__ = "trusted_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_trusted_channels_user_channel"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Multiplier applied to the trust component of the score.
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
