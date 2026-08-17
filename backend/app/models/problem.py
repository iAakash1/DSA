"""Canonical problem entity plus the topic / pattern taxonomy.

A problem has exactly one canonical identity — `(platform, external_id)` —
regardless of how many sheets, collections or contests reference it.
"""

from __future__ import annotations

import uuid

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
from app.db.types import GUID, JSONType


class Problem(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_problems_platform_external_id"),
        Index("ix_problems_rating", "rating"),
        Index("ix_problems_difficulty", "difficulty"),
    )

    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: Canonical per-platform id: LeetCode slug ("two-sum"), Codeforces "1400B".
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    difficulty: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    #: Codeforces-style numeric rating. LeetCode problems may carry an inferred
    #: rating from an imported dataset — `rating_source` records provenance.
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_source: Mapped[str | None] = mapped_column(String(32))

    acceptance_rate: Mapped[float | None] = mapped_column(Float)
    solved_count: Mapped[int | None] = mapped_column(Integer)

    # Codeforces decomposition, null for LeetCode.
    contest_id: Mapped[int | None] = mapped_column(Integer, index=True)
    problem_index: Mapped[str | None] = mapped_column(String(8))

    #: Raw platform tags, kept verbatim for provenance. The normalized view
    #: lives in `problem_topics` / `problem_patterns`.
    tags: Mapped[list | None] = mapped_column(JSONType)
    extra: Mapped[dict | None] = mapped_column(JSONType)

    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Progressive hints carried by the source sheet, ordered least- to
    #: most-revealing. Global to the problem, never user-specific.
    hints: Mapped[list | None] = mapped_column(JSONType)
    #: Editorial/solution video URLs supplied by the source sheet. Discovered
    #: videos live in `resources`; these are the curator's own links.
    video_links: Mapped[list | None] = mapped_column(JSONType)
    metadata_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    topics: Mapped[list["ProblemTopic"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )
    patterns: Mapped[list["ProblemPattern"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )

    @property
    def canonical_id(self) -> str:
        return f"{self.platform}:{self.external_id}"


class Topic(UUIDPrimaryKey, Timestamps, Base):
    """Hierarchical topic node.

    Self-referential parent link gives arbitrary depth:
    Graphs -> Shortest Path -> Dijkstra.
    """

    __tablename__ = "topics"

    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="topic", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Materialized ancestor path ("graphs/shortest-path/dijkstra") so rollups
    #: do not need a recursive CTE on every analytics query.
    path: Mapped[str] = mapped_column(String(512), default="", nullable=False, index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    parent: Mapped["Topic | None"] = relationship(remote_side="Topic.id", back_populates="children")
    children: Mapped[list["Topic"]] = relationship(back_populates="parent")


class Pattern(UUIDPrimaryKey, Timestamps, Base):
    """A solving pattern — deliberately separate from topic.

    "Dynamic Programming" is a topic; "1D DP" is a pattern; "state compression"
    is a technique. Collapsing them loses the signal that matters most for
    diagnosing weakness.
    """

    __tablename__ = "patterns"

    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("topics.id", ondelete="SET NULL"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Patterns worth revisiting even after a successful solve.
    is_core: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    topic: Mapped[Topic | None] = relationship()


class ProblemTopic(Base):
    __tablename__ = "problem_topics"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    #: platform | sheet | manual — lets us prefer curated over auto-derived.
    source: Mapped[str] = mapped_column(String(32), default="platform", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    problem: Mapped[Problem] = relationship(back_populates="topics")
    topic: Mapped[Topic] = relationship()


class ProblemPattern(Base):
    __tablename__ = "problem_patterns"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), default="platform", nullable=False)

    problem: Mapped[Problem] = relationship(back_populates="patterns")
    pattern: Mapped[Pattern] = relationship()
