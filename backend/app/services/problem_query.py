"""Problem explorer queries: filtering, search, sorting, pagination."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.analytics.core import SOLVED_STATUSES
from app.models.enums import ProblemStatus
from app.models.problem import (
    Pattern,
    Problem,
    ProblemPattern,
    ProblemTopic,
    Topic,
)
from app.models.progress import Mistake, ProblemNote, Review, SolvingSession, UserProblem
from app.models.sheet import Collection, CollectionProblem, Sheet, SheetProblem, SheetSection

SORT_FIELDS = {
    "title": Problem.title,
    "rating": Problem.rating,
    "difficulty": Problem.difficulty,
    "recently_added": Problem.created_at,
    "recently_solved": UserProblem.last_solved_at,
    "time_taken": UserProblem.total_time_seconds,
}


def search_problems(
    db: Session,
    user_id: uuid.UUID,
    *,
    query: str | None = None,
    platform: str | None = None,
    sheet: str | None = None,
    section: str | None = None,
    topic: str | None = None,
    pattern: str | None = None,
    collection: str | None = None,
    status: str | None = None,
    difficulty: str | None = None,
    min_rating: int | None = None,
    max_rating: int | None = None,
    needs_review: bool | None = None,
    has_notes: bool | None = None,
    solved_independently: bool | None = None,
    sort: str = "recently_added",
    direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filtered, paginated problem list scoped to one user's progress."""
    stmt = select(Problem, UserProblem).outerjoin(
        UserProblem,
        (UserProblem.problem_id == Problem.id) & (UserProblem.user_id == user_id),
    )

    if query:
        term = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Problem.title).like(term),
                func.lower(Problem.external_id).like(term),
                func.lower(Problem.slug).like(term),
            )
        )

    if platform:
        stmt = stmt.where(Problem.platform == platform)
    if difficulty:
        stmt = stmt.where(Problem.difficulty == difficulty)
    if min_rating is not None:
        stmt = stmt.where(Problem.rating >= min_rating)
    if max_rating is not None:
        stmt = stmt.where(Problem.rating <= max_rating)

    if sheet:
        stmt = stmt.join(SheetProblem, SheetProblem.problem_id == Problem.id).join(
            Sheet, Sheet.id == SheetProblem.sheet_id
        ).where(Sheet.slug == sheet)
        if section:
            stmt = stmt.join(
                SheetSection, SheetSection.id == SheetProblem.section_id
            ).where(SheetSection.slug == section)

    if topic:
        # Include descendants so filtering by "Graphs" catches Dijkstra.
        node = db.scalar(select(Topic).where(Topic.slug == topic))
        if node is not None:
            descendants = select(Topic.id).where(
                (Topic.path == node.path) | (Topic.path.like(f"{node.path}/%"))
            )
            stmt = stmt.where(
                Problem.id.in_(
                    select(ProblemTopic.problem_id).where(
                        ProblemTopic.topic_id.in_(descendants)
                    )
                )
            )

    if pattern:
        stmt = stmt.where(
            Problem.id.in_(
                select(ProblemPattern.problem_id)
                .join(Pattern, Pattern.id == ProblemPattern.pattern_id)
                .where(Pattern.slug == pattern)
            )
        )

    if collection:
        stmt = stmt.where(
            Problem.id.in_(
                select(CollectionProblem.problem_id)
                .join(Collection, Collection.id == CollectionProblem.collection_id)
                .where(Collection.user_id == user_id, Collection.slug == collection)
            )
        )

    if status:
        if status == ProblemStatus.UNSOLVED:
            stmt = stmt.where(
                (UserProblem.status.is_(None))
                | (UserProblem.status == ProblemStatus.UNSOLVED)
            )
        elif status == "completed":
            stmt = stmt.where(UserProblem.status.in_(SOLVED_STATUSES))
        else:
            stmt = stmt.where(UserProblem.status == status)

    if needs_review:
        stmt = stmt.where(UserProblem.needs_review.is_(True))
    if solved_independently:
        stmt = stmt.where(UserProblem.best_solution_source == "independent")
    if has_notes:
        stmt = stmt.where(
            Problem.id.in_(
                select(ProblemNote.problem_id).where(ProblemNote.user_id == user_id)
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = SORT_FIELDS.get(sort, Problem.created_at)
    stmt = stmt.order_by(column.desc() if direction == "desc" else column.asc())

    rows = db.execute(stmt.limit(min(limit, 200)).offset(offset)).all()

    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": [serialize_problem(p, up) for p, up in rows],
    }


def serialize_problem(problem: Problem, user_problem: UserProblem | None) -> dict[str, Any]:
    return {
        "id": str(problem.id),
        "platform": problem.platform,
        "external_id": problem.external_id,
        "canonical_id": problem.canonical_id,
        #: Readable stand-in where the identity is not — takeUforward problems
        #: are keyed by a numeric id nobody would recognise.
        "slug": problem.slug,
        "title": problem.title,
        "url": problem.url,
        "rating": problem.rating,
        "difficulty": problem.difficulty,
        "tags": problem.tags or [],
        "is_premium": problem.is_premium,
        "status": user_problem.status if user_problem else ProblemStatus.UNSOLVED,
        "attempts": user_problem.attempts if user_problem else 0,
        "solved_at": user_problem.first_solved_at.isoformat()
        if user_problem and user_problem.first_solved_at
        else None,
        "solution_source": user_problem.best_solution_source if user_problem else None,
        "confidence": user_problem.confidence if user_problem else None,
        "needs_review": bool(user_problem.needs_review) if user_problem else False,
        "is_favorite": bool(user_problem.is_favorite) if user_problem else False,
        "time_spent_seconds": user_problem.total_time_seconds if user_problem else 0,
    }


def problem_detail(
    db: Session, user_id: uuid.UUID, problem_id: uuid.UUID
) -> dict[str, Any]:
    """Everything the problem page shows, in one round trip."""
    from app.core.errors import NotFoundError
    from app.models.editorial import Resource
    from app.recommendations.engine import related_problems

    problem = db.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError("Problem not found")

    user_problem = db.scalar(
        select(UserProblem).where(
            UserProblem.user_id == user_id, UserProblem.problem_id == problem_id
        )
    )

    topics = db.execute(
        select(Topic.slug, Topic.name, Topic.path)
        .join(ProblemTopic, ProblemTopic.topic_id == Topic.id)
        .where(ProblemTopic.problem_id == problem_id)
    ).all()
    patterns = db.execute(
        select(Pattern.slug, Pattern.name)
        .join(ProblemPattern, ProblemPattern.pattern_id == Pattern.id)
        .where(ProblemPattern.problem_id == problem_id)
    ).all()

    sheets = db.execute(
        select(Sheet.slug, Sheet.name, SheetSection.name, SheetSection.rating_bucket)
        .select_from(SheetProblem)
        .join(Sheet, Sheet.id == SheetProblem.sheet_id)
        .outerjoin(SheetSection, SheetSection.id == SheetProblem.section_id)
        .where(SheetProblem.problem_id == problem_id)
    ).all()

    collections = db.execute(
        select(Collection.slug, Collection.name)
        .join(CollectionProblem, CollectionProblem.collection_id == Collection.id)
        .where(
            CollectionProblem.problem_id == problem_id, Collection.user_id == user_id
        )
    ).all()

    sessions = db.scalars(
        select(SolvingSession)
        .where(
            SolvingSession.user_id == user_id, SolvingSession.problem_id == problem_id
        )
        .order_by(SolvingSession.created_at.desc())
        .limit(20)
    ).all()

    notes = db.scalars(
        select(ProblemNote)
        .where(ProblemNote.user_id == user_id, ProblemNote.problem_id == problem_id)
        .order_by(ProblemNote.created_at.desc())
    ).all()

    mistakes = db.scalars(
        select(Mistake)
        .where(Mistake.user_id == user_id, Mistake.problem_id == problem_id)
        .order_by(Mistake.occurred_at.desc())
    ).all()

    resources = db.scalars(
        select(Resource)
        .where(Resource.problem_id == problem_id)
        .order_by(Resource.is_selected.desc(), Resource.score.desc())
        .limit(10)
    ).all()

    review = db.scalar(
        select(Review)
        .where(
            Review.user_id == user_id,
            Review.problem_id == problem_id,
            Review.completed_at.is_(None),
        )
        .order_by(Review.scheduled_for)
    )

    return {
        **serialize_problem(problem, user_problem),
        "topics": [{"slug": s, "name": n, "path": p} for s, n, p in topics],
        "patterns": [{"slug": s, "name": n} for s, n in patterns],
        "sheets": [
            {"slug": s, "name": n, "section": sec, "rating_bucket": bucket}
            for s, n, sec, bucket in sheets
        ],
        "collections": [{"slug": s, "name": n} for s, n in collections],
        "sessions": [
            {
                "id": str(s.id),
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "time_spent_seconds": s.time_spent_seconds,
                "attempt_count": s.attempt_count,
                "result": s.result,
                "solution_source": s.solution_source,
                "confidence": s.confidence,
                "difficulty_perception": s.difficulty_perception,
                "approach": s.approach,
                "notes": s.notes,
            }
            for s in sessions
        ],
        "notes": [
            {
                "id": str(n.id),
                "kind": n.kind,
                "content_md": n.content_md,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ],
        "mistakes": [
            {
                "id": str(m.id),
                "type": m.mistake_type,
                "note": m.note,
                "occurred_at": m.occurred_at.isoformat(),
            }
            for m in mistakes
        ],
        "resources": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "title": r.title,
                "url": r.url,
                "channel_title": r.channel_title,
                "duration_seconds": r.duration_seconds,
                "score": r.score,
                "is_selected": r.is_selected,
                "external_id": r.external_id,
            }
            for r in resources
        ],
        "review": {
            "id": str(review.id),
            "reason": review.reason,
            "reason_detail": review.reason_detail,
            "scheduled_for": review.scheduled_for.isoformat(),
        }
        if review
        else None,
        "related": related_problems(db, problem_id),
    }


def global_search(
    db: Session, user_id: uuid.UUID, term: str, limit: int = 10
) -> dict[str, Any]:
    """Command-palette search across problems, topics, patterns and sheets."""
    like = f"%{term.strip().lower()}%"

    problems = db.execute(
        select(Problem, UserProblem)
        .outerjoin(
            UserProblem,
            (UserProblem.problem_id == Problem.id) & (UserProblem.user_id == user_id),
        )
        .where(
            or_(
                func.lower(Problem.title).like(like),
                func.lower(Problem.external_id).like(like),
            )
        )
        .limit(limit)
    ).all()

    topics = db.scalars(
        select(Topic).where(func.lower(Topic.name).like(like)).limit(5)
    ).all()
    patterns = db.scalars(
        select(Pattern).where(func.lower(Pattern.name).like(like)).limit(5)
    ).all()
    sheets = db.scalars(
        select(Sheet).where(func.lower(Sheet.name).like(like)).limit(5)
    ).all()

    return {
        "problems": [serialize_problem(p, up) for p, up in problems],
        "topics": [{"slug": t.slug, "name": t.name} for t in topics],
        "patterns": [{"slug": p.slug, "name": p.name} for p in patterns],
        "sheets": [{"slug": s.slug, "name": s.name} for s in sheets],
    }
