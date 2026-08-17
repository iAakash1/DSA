"""Problem explorer, problem page, and everything that records progress."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError, ValidationError
from app.models.progress import Mistake, ProblemNote
from app.schemas.requests import (
    AddProblemRequest,
    MistakeRequest,
    NoteRequest,
    RecordAttemptRequest,
    RecordSolveRequest,
    StatusUpdate,
)
from app.services import problem_query, sheet_service
from app.services.problem_service import (
    add_problem_from_reference,
    require_problem,
)
from app.services.solve_service import record_attempt, record_solve, set_status
from app.utils.timeutils import utcnow

router = APIRouter(prefix="/problems", tags=["problems"])


def _uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"{field} must be a UUID") from exc


@router.get("")
def list_problems(
    db: DbSession,
    user: CurrentUser,
    q: str | None = None,
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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    return problem_query.search_problems(
        db,
        user.id,
        query=q,
        platform=platform,
        sheet=sheet,
        section=section,
        topic=topic,
        pattern=pattern,
        collection=collection,
        status=status,
        difficulty=difficulty,
        min_rating=min_rating,
        max_rating=max_rating,
        needs_review=needs_review,
        has_notes=has_notes,
        solved_independently=solved_independently,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201)
def add_problem(payload: AddProblemRequest, db: DbSession, user: CurrentUser) -> dict:
    """Add a problem from a pasted LeetCode/Codeforces URL or identifier."""
    problem, created = add_problem_from_reference(
        db,
        payload.reference,
        platform=payload.platform,
        title=payload.title,
        difficulty=payload.difficulty,
        rating=payload.rating,
        tags=payload.tags,
    )

    # Default new problems into the Inbox so nothing gets lost.
    target = payload.collection or "inbox"
    try:
        sheet_service.add_to_collection(db, user.id, target, problem.id)
    except NotFoundError:
        pass

    return {
        **problem_query.serialize_problem(problem, None),
        "created": created,
        "collection": target,
    }


@router.get("/search")
def search(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(min_length=1),
    limit: int = Query(10, ge=1, le=30),
) -> dict:
    return problem_query.global_search(db, user.id, q, limit)


@router.get("/{problem_id}")
def get_problem(problem_id: str, db: DbSession, user: CurrentUser) -> dict:
    return problem_query.problem_detail(db, user.id, _uuid(problem_id))


@router.post("/{problem_id}/solve")
def solve(
    problem_id: str, payload: RecordSolveRequest, db: DbSession, user: CurrentUser
) -> dict:
    result = record_solve(
        db,
        user.id,
        _uuid(problem_id),
        solved_at=payload.solved_at,
        solution_source=payload.solution_source,
        time_spent_seconds=payload.time_spent_seconds,
        attempt_count=payload.attempt_count,
        confidence=payload.confidence,
        difficulty_perception=payload.difficulty_perception,
        approach=payload.approach,
        notes=payload.notes,
        mistakes=[m.value for m in payload.mistakes],
    )
    return result.as_dict()


@router.post("/{problem_id}/attempt")
def attempt(
    problem_id: str, payload: RecordAttemptRequest, db: DbSession, user: CurrentUser
) -> dict:
    user_problem = record_attempt(
        db,
        user.id,
        _uuid(problem_id),
        attempted_at=payload.attempted_at,
        verdict=payload.verdict,
        time_spent_seconds=payload.time_spent_seconds,
        notes=payload.notes,
        mistakes=[m.value for m in payload.mistakes],
    )
    return {"status": user_problem.status, "attempts": user_problem.attempts}


@router.patch("/{problem_id}/status")
def update_status(
    problem_id: str, payload: StatusUpdate, db: DbSession, user: CurrentUser
) -> dict:
    user_problem = set_status(db, user.id, _uuid(problem_id), payload.status)
    return {"status": user_problem.status}


@router.post("/{problem_id}/notes", status_code=201)
def add_note(
    problem_id: str, payload: NoteRequest, db: DbSession, user: CurrentUser
) -> dict:
    pid = _uuid(problem_id)
    require_problem(db, pid)
    note = ProblemNote(
        user_id=user.id, problem_id=pid, kind=payload.kind, content_md=payload.content_md
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {
        "id": str(note.id),
        "kind": note.kind,
        "content_md": note.content_md,
        "created_at": note.created_at.isoformat(),
    }


@router.delete("/{problem_id}/notes/{note_id}")
def delete_note(
    problem_id: str, note_id: str, db: DbSession, user: CurrentUser
) -> dict:
    note = db.get(ProblemNote, _uuid(note_id, "note_id"))
    if note is None or note.user_id != user.id:
        raise NotFoundError("Note not found")
    db.delete(note)
    db.commit()
    return {"deleted": note_id}


@router.post("/{problem_id}/mistakes", status_code=201)
def add_mistake(
    problem_id: str, payload: MistakeRequest, db: DbSession, user: CurrentUser
) -> dict:
    pid = _uuid(problem_id)
    require_problem(db, pid)
    mistake = Mistake(
        user_id=user.id,
        problem_id=pid,
        mistake_type=payload.mistake_type,
        note=payload.note,
        occurred_at=utcnow(),
    )
    db.add(mistake)
    db.commit()
    db.refresh(mistake)
    return {
        "id": str(mistake.id),
        "type": mistake.mistake_type,
        "occurred_at": mistake.occurred_at.isoformat(),
    }


@router.get("/{problem_id}/resources")
def resources(
    problem_id: str,
    db: DbSession,
    user: CurrentUser,
    refresh: bool = False,
) -> dict:
    """Editorial videos for a problem, from trusted channels only."""
    from app.services.editorial_service import get_resources

    return get_resources(db, user.id, _uuid(problem_id), refresh=refresh)
