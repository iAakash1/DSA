"""Sheets (Striver A2Z, CP-31) and user collections.

A sheet is a curated ordering over canonical problems. Membership never
duplicates the problem itself.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import GUID, JSONType

if TYPE_CHECKING:
    from app.models.problem import Problem


class Sheet(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "sheets"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="custom", nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Provenance of the imported corpus: source_name, source_url,
    #: source_version, source_hash, imported_at, parser_version, row counts.
    #: Lets the UI state exactly which version of a sheet is loaded, and makes
    #: a re-import from a different version detectable rather than silent.
    source_metadata: Mapped[dict | None] = mapped_column(JSONType)

    sections: Mapped[list["SheetSection"]] = relationship(
        back_populates="sheet",
        cascade="all, delete-orphan",
        order_by="SheetSection.sort_order",
    )


class SheetSection(UUIDPrimaryKey, Timestamps, Base):
    """A section within a sheet.

    Striver sections are topics ("Binary Search"); CP-31 sections are rating
    buckets (800, 900, ...). `rating_bucket` is set only for the latter.
    """

    __tablename__ = "sheet_sections"
    __table_args__ = (
        UniqueConstraint("sheet_id", "slug", name="uq_sheet_sections_sheet_slug"),
    )

    sheet_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("sheets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="topic", nullable=False)
    rating_bucket: Mapped[int | None] = mapped_column(Integer, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Optional link into the global taxonomy so sheet progress and topic
    #: mastery can be reconciled.
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("topics.id", ondelete="SET NULL")
    )

    sheet: Mapped[Sheet] = relationship(back_populates="sections")
    problems: Mapped[list["SheetProblem"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="SheetProblem.order_index",
    )


class SheetProblem(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "sheet_problems"
    __table_args__ = (
        UniqueConstraint("sheet_id", "problem_id", name="uq_sheet_problems_sheet_problem"),
    )

    sheet_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("sheets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("sheet_sections.id", ondelete="SET NULL"), index=True
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    #: Every row in the source sheet that resolves to this canonical problem.
    #:
    #: A sheet may list one problem more than once — Striver A2Z reaches the
    #: same LeetCode problem from several angles ("Left Rotate Array by One"
    #: and "by K Places" are both `rotate-array`). Progress must collapse onto
    #: the canonical problem, or solving it once would leave a phantom
    #: unsolved twin. But the entries are distinct exercises, so dropping them
    #: would quietly shrink the sheet. They are kept here instead: one
    #: membership, all of its source rows.
    source_entries: Mapped[list | None] = mapped_column(JSONType)

    section: Mapped[SheetSection | None] = relationship(back_populates="problems")
    sheet: Mapped[Sheet] = relationship()
    problem: Mapped["Problem"] = relationship()


class Collection(UUIDPrimaryKey, Timestamps, Base):
    """A user-owned problem list (ICPC Prep, Revision, Mistakes, Inbox...)."""

    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_collections_user_slug"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(16))
    icon: Mapped[str | None] = mapped_column(String(32))
    #: System collections (Inbox, Favorites) cannot be deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    items: Mapped[list["CollectionProblem"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionProblem(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "collection_problems"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "problem_id", name="uq_collection_problems_collection_problem"
        ),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("collections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collection: Mapped[Collection] = relationship(back_populates="items")
    problem: Mapped["Problem"] = relationship()
