"""AI insight cache, conversations and usage accounting.

Insights are cached against a `data_snapshot_hash` of the deterministic
analytics that produced them: if the underlying numbers have not changed there
is no reason to spend a token regenerating the interpretation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, JSONType, UTCDateTime


class AIInsight(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ai_insights"
    __table_args__ = (
        Index("ix_ai_insights_user_type_generated", "user_id", "type", "generated_at"),
        Index("ix_ai_insights_snapshot", "user_id", "type", "data_snapshot_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    #: Validated structured payload (evidence, diagnosis, recommendations).
    structured_output: Mapped[dict | None] = mapped_column(JSONType)
    #: The exact deterministic metrics handed to the model, for "Why am I
    #: seeing this?" and for auditing hallucinations.
    context_snapshot: Mapped[dict | None] = mapped_column(JSONType)

    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    data_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)

    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    #: Optional scoping (e.g. contest analysis is tied to one contest).
    subject_id: Mapped[uuid.UUID | None] = mapped_column(GUID, index=True)


class AIConversation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ai_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="New conversation", nullable=False)
    #: Rolling summary so old turns can be dropped without losing thread.
    summary: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIMessage.created_at",
    )


class AIMessage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_conversation", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: Which analytics tools the model called to ground this answer.
    tool_calls: Mapped[list | None] = mapped_column(JSONType)
    tokens: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(128))

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")


class AIUsage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
