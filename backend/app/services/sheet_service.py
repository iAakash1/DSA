"""Sheet progress (CP-31, Striver A2Z) and collections."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import SOLVED_STATUSES, safe_ratio
from app.core.errors import NotFoundError, ValidationError
from app.models.enums import ProblemStatus
from app.models.problem import Problem
from app.models.progress import UserProblem
from app.models.sheet import (
    Collection,
    CollectionProblem,
    Sheet,
    SheetProblem,
    SheetSection,
)
from app.utils.normalize import slugify


#: Observed from the signed-in CP-31 page: 12 buckets x 31 = 372.
#: Until an authoritative export is imported, the bundled seed is partial and
#: the UI must say so rather than showing a completion percentage of a
#: corpus we do not actually hold.
EXPECTED_TOTALS = {"cp31": 372, "striver-a2z": 455}


def dataset_status(slug: str, loaded: int) -> dict[str, Any]:
    expected = EXPECTED_TOTALS.get(slug)
    if expected is None:
        return {"state": "complete", "loaded": loaded, "expected": None, "label": None}
    if loaded >= expected:
        return {"state": "complete", "loaded": loaded, "expected": expected, "label": None}
    return {
        "state": "partial",
        "loaded": loaded,
        "expected": expected,
        "label": "Partial dataset — authoritative import required",
    }


def _status_counts(
    db: Session, user_id: uuid.UUID, sheet_id: uuid.UUID, section_id: uuid.UUID | None = None
) -> dict[str, int]:
    """Solved / attempted / skipped / unsolved for a sheet or one section."""
    query = (
        select(UserProblem.status, func.count(SheetProblem.id))
        .select_from(SheetProblem)
        .outerjoin(
            UserProblem,
            (UserProblem.problem_id == SheetProblem.problem_id)
            & (UserProblem.user_id == user_id),
        )
        .where(SheetProblem.sheet_id == sheet_id)
        .group_by(UserProblem.status)
    )
    if section_id is not None:
        query = query.where(SheetProblem.section_id == section_id)

    counts = {
        "solved": 0,
        "attempted": 0,
        "skipped": 0,
        "unsolved": 0,
        "revisit": 0,
        "mastered": 0,
    }
    for status, count in db.execute(query).all():
        count = int(count)
        if status is None or status == ProblemStatus.UNSOLVED:
            counts["unsolved"] += count
        elif status in counts:
            counts[status] += count

    counts["total"] = sum(
        v for k, v in counts.items() if k != "total"
    )
    counts["completed"] = counts["solved"] + counts["mastered"] + counts["revisit"]
    counts["percent"] = round(safe_ratio(counts["completed"], max(1, counts["total"])) * 100, 1)
    return counts


def list_sheets(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    sheets = db.scalars(select(Sheet).order_by(Sheet.sort_order, Sheet.name)).all()
    return [
        {
            "id": str(sheet.id),
            "slug": sheet.slug,
            "name": sheet.name,
            "kind": sheet.kind,
            "description": sheet.description,
            "source_url": sheet.source_url,
            "progress": _status_counts(db, user_id, sheet.id),
            "dataset": dataset_status(
                sheet.slug, _status_counts(db, user_id, sheet.id)["total"]
            ),
        }
        for sheet in sheets
    ]


def require_sheet(db: Session, slug: str) -> Sheet:
    sheet = db.scalar(select(Sheet).where(Sheet.slug == slug))
    if sheet is None:
        raise NotFoundError(
            f"Sheet {slug!r} has not been imported yet. Run `make seed` or use the import API."
        )
    return sheet


def sheet_detail(db: Session, user_id: uuid.UUID, slug: str) -> dict[str, Any]:
    sheet = require_sheet(db, slug)
    sections = db.scalars(
        select(SheetSection)
        .where(SheetSection.sheet_id == sheet.id)
        .order_by(SheetSection.sort_order)
    ).all()

    return {
        "id": str(sheet.id),
        "slug": sheet.slug,
        "name": sheet.name,
        "kind": sheet.kind,
        "description": sheet.description,
        "source_url": sheet.source_url,
        "progress": _status_counts(db, user_id, sheet.id),
        "dataset": dataset_status(
            sheet.slug, _status_counts(db, user_id, sheet.id)["total"]
        ),
        "sections": [
            {
                "id": str(section.id),
                "slug": section.slug,
                "name": section.name,
                "kind": section.kind,
                "rating_bucket": section.rating_bucket,
                "progress": _status_counts(db, user_id, sheet.id, section.id),
            }
            for section in sections
        ],
    }


def sheet_problems(
    db: Session,
    user_id: uuid.UUID,
    slug: str,
    *,
    section: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    sheet = require_sheet(db, slug)

    query = (
        select(SheetProblem, Problem, UserProblem, SheetSection)
        .join(Problem, Problem.id == SheetProblem.problem_id)
        .outerjoin(
            UserProblem,
            (UserProblem.problem_id == SheetProblem.problem_id)
            & (UserProblem.user_id == user_id),
        )
        .outerjoin(SheetSection, SheetSection.id == SheetProblem.section_id)
        .where(SheetProblem.sheet_id == sheet.id)
        .order_by(SheetSection.sort_order, SheetProblem.order_index)
    )

    if section:
        query = query.where(SheetSection.slug == section)
    if status:
        if status == ProblemStatus.UNSOLVED:
            query = query.where(
                (UserProblem.status.is_(None))
                | (UserProblem.status == ProblemStatus.UNSOLVED)
            )
        elif status == "completed":
            query = query.where(UserProblem.status.in_(SOLVED_STATUSES))
        else:
            query = query.where(UserProblem.status == status)

    total = db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    rows = db.execute(query.limit(limit).offset(offset)).all()

    return {
        "sheet": {"slug": sheet.slug, "name": sheet.name, "kind": sheet.kind},
        "total": int(total),
        "items": [
            {
                "problem_id": str(problem.id),
                "title": problem.title,
                "platform": problem.platform,
                "external_id": problem.external_id,
                "url": problem.url,
                "rating": problem.rating,
                "difficulty": problem.difficulty,
                "tags": problem.tags or [],
                "section": section_row.slug if section_row else None,
                "section_name": section_row.name if section_row else None,
                "rating_bucket": section_row.rating_bucket if section_row else None,
                "order": sheet_problem.order_index,
                "status": user_problem.status if user_problem else ProblemStatus.UNSOLVED,
                "solved_at": user_problem.first_solved_at.isoformat()
                if user_problem and user_problem.first_solved_at
                else None,
                "solution_source": user_problem.best_solution_source
                if user_problem
                else None,
                "needs_review": bool(user_problem.needs_review) if user_problem else False,
            }
            for sheet_problem, problem, user_problem, section_row in rows
        ],
    }


def next_unsolved_in_sheet(
    db: Session, user_id: uuid.UUID, slug: str, limit: int = 5
) -> list[Problem]:
    """The next problems to attempt, respecting sheet order."""
    sheet = db.scalar(select(Sheet).where(Sheet.slug == slug))
    if sheet is None:
        return []

    rows = db.execute(
        select(Problem)
        .select_from(SheetProblem)
        .join(Problem, Problem.id == SheetProblem.problem_id)
        .outerjoin(SheetSection, SheetSection.id == SheetProblem.section_id)
        .outerjoin(
            UserProblem,
            (UserProblem.problem_id == SheetProblem.problem_id)
            & (UserProblem.user_id == user_id),
        )
        .where(
            SheetProblem.sheet_id == sheet.id,
            (UserProblem.status.is_(None))
            | (UserProblem.status.in_((ProblemStatus.UNSOLVED, ProblemStatus.ATTEMPTED))),
        )
        .order_by(SheetSection.sort_order, SheetProblem.order_index)
        .limit(limit)
    ).all()
    return [row[0] for row in rows]


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def list_collections(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    collections = db.scalars(
        select(Collection)
        .where(Collection.user_id == user_id)
        .order_by(Collection.is_system.desc(), Collection.sort_order, Collection.name)
    ).all()

    counts = dict(
        db.execute(
            select(CollectionProblem.collection_id, func.count(CollectionProblem.id))
            .join(Collection, Collection.id == CollectionProblem.collection_id)
            .where(Collection.user_id == user_id)
            .group_by(CollectionProblem.collection_id)
        ).all()
    )

    return [
        {
            "id": str(collection.id),
            "slug": collection.slug,
            "name": collection.name,
            "description": collection.description,
            "color": collection.color,
            "icon": collection.icon,
            "is_system": collection.is_system,
            "count": int(counts.get(collection.id, 0)),
        }
        for collection in collections
    ]


def create_collection(
    db: Session, user_id: uuid.UUID, name: str, **fields
) -> Collection:
    name = (name or "").strip()
    if not name:
        raise ValidationError("A collection needs a name")

    slug = slugify(name)
    existing = db.scalar(
        select(Collection).where(Collection.user_id == user_id, Collection.slug == slug)
    )
    if existing is not None:
        raise ValidationError(f"You already have a collection called {name!r}")

    collection = Collection(user_id=user_id, slug=slug, name=name, **fields)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def require_collection(db: Session, user_id: uuid.UUID, slug: str) -> Collection:
    collection = db.scalar(
        select(Collection).where(Collection.user_id == user_id, Collection.slug == slug)
    )
    if collection is None:
        raise NotFoundError(f"Collection {slug!r} not found")
    return collection


def add_to_collection(
    db: Session,
    user_id: uuid.UUID,
    slug: str,
    problem_id: uuid.UUID,
    note: str | None = None,
) -> CollectionProblem:
    collection = require_collection(db, user_id, slug)
    existing = db.scalar(
        select(CollectionProblem).where(
            CollectionProblem.collection_id == collection.id,
            CollectionProblem.problem_id == problem_id,
        )
    )
    if existing is not None:
        return existing

    position = int(
        db.scalar(
            select(func.coalesce(func.max(CollectionProblem.position), 0)).where(
                CollectionProblem.collection_id == collection.id
            )
        )
        or 0
    )
    item = CollectionProblem(
        collection_id=collection.id,
        problem_id=problem_id,
        note=note,
        position=position + 1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def remove_from_collection(
    db: Session, user_id: uuid.UUID, slug: str, problem_id: uuid.UUID
) -> None:
    collection = require_collection(db, user_id, slug)
    item = db.scalar(
        select(CollectionProblem).where(
            CollectionProblem.collection_id == collection.id,
            CollectionProblem.problem_id == problem_id,
        )
    )
    if item is None:
        raise NotFoundError("That problem is not in this collection")
    db.delete(item)
    db.commit()


def collection_problems(
    db: Session, user_id: uuid.UUID, slug: str
) -> list[dict[str, Any]]:
    collection = require_collection(db, user_id, slug)
    rows = db.execute(
        select(Problem, UserProblem, CollectionProblem)
        .select_from(CollectionProblem)
        .join(Problem, Problem.id == CollectionProblem.problem_id)
        .outerjoin(
            UserProblem,
            (UserProblem.problem_id == CollectionProblem.problem_id)
            & (UserProblem.user_id == user_id),
        )
        .where(CollectionProblem.collection_id == collection.id)
        .order_by(CollectionProblem.position)
    ).all()

    return [
        {
            "problem_id": str(problem.id),
            "title": problem.title,
            "platform": problem.platform,
            "external_id": problem.external_id,
            "url": problem.url,
            "rating": problem.rating,
            "difficulty": problem.difficulty,
            "status": user_problem.status if user_problem else ProblemStatus.UNSOLVED,
            "note": item.note,
        }
        for problem, user_problem, item in rows
    ]
