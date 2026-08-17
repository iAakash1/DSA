"""Contest tracking and upsolving."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.schemas.requests import ContestRequest, UpsolveRequest
from app.services import contest_service

router = APIRouter(prefix="/contests", tags=["contests"])


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"{field} must be a UUID") from exc


@router.get("")
def list_contests(
    db: DbSession, user: CurrentUser, limit: int = Query(20, ge=1, le=100)
) -> dict:
    return {
        "summary": contest_service.contest_summary(db, user.id),
        "items": contest_service.contest_history(db, user.id, limit),
    }


@router.post("", status_code=201)
def add_contest(payload: ContestRequest, db: DbSession, user: CurrentUser) -> dict:
    participation = contest_service.record_participation(
        db, user.id, payload.model_dump()
    )
    return {
        "id": str(participation.id),
        "contest_id": str(participation.contest_id),
        "rank": participation.rank,
        "rating_change": participation.rating_change,
    }


@router.post("/sync/codeforces")
def sync_codeforces(db: DbSession, user: CurrentUser) -> dict:
    return contest_service.sync_codeforces_contests(db, user.id)


@router.post("/{contest_id}/problems")
def set_problem_result(
    contest_id: str, payload: UpsolveRequest, db: DbSession, user: CurrentUser
) -> dict:
    result = contest_service.set_problem_result(
        db,
        user.id,
        _uuid(contest_id, "contest_id"),
        _uuid(payload.problem_id, "problem_id"),
        payload.status,
    )
    return {
        "problem_id": str(result.problem_id),
        "status": result.status,
        "solved_at": result.solved_at.isoformat() if result.solved_at else None,
    }
