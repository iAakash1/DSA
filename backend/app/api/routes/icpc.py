"""ICPC mode: countdown, roadmap, template library, virtual contests, readiness."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.schemas.requests import (
    ICPCSettingsRequest,
    TemplateReviewRequest,
    TopicProgressRequest,
    VirtualContestProblemRequest,
    VirtualContestRequest,
)
from app.services import icpc_service

router = APIRouter(prefix="/icpc", tags=["icpc"])


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"{field} must be a UUID") from exc


@router.get("")
def icpc_dashboard(db: DbSession, user: CurrentUser) -> dict:
    return icpc_service.dashboard(db, user.id, user.timezone)


@router.put("/settings")
def update_settings(
    payload: ICPCSettingsRequest, db: DbSession, user: CurrentUser
) -> dict:
    settings = icpc_service.update_settings(
        db,
        user.id,
        target_date=payload.target_date,
        team_name=payload.team_name,
        weekly_practice_days=payload.weekly_practice_days,
        target_rating=payload.target_rating,
        focus_topics=payload.focus_topics,
        enabled=payload.enabled,
    )
    return {
        "target_date": settings.target_date.isoformat() if settings.target_date else None,
        "team_name": settings.team_name,
        "weekly_practice_days": settings.weekly_practice_days,
        "target_rating": settings.target_rating,
        "focus_topics": settings.focus_topics or [],
        "enabled": settings.enabled,
        "countdown": icpc_service.countdown(settings, user.timezone),
    }


@router.get("/roadmap")
def roadmap(db: DbSession, user: CurrentUser) -> dict:
    return icpc_service.roadmap(db, user.id, user.timezone)


@router.put("/roadmap/{topic_key}")
def update_topic(
    topic_key: str, payload: TopicProgressRequest, db: DbSession, user: CurrentUser
) -> dict:
    row = icpc_service.set_topic_progress(
        db,
        user.id,
        topic_key,
        studied=payload.studied,
        template_reviewed=payload.template_reviewed,
        confidence=payload.confidence,
        notes=payload.notes,
    )
    return {
        "topic_key": row.topic_key,
        "studied": row.studied,
        "template_reviewed": row.template_reviewed,
        "confidence": row.confidence,
        "notes": row.notes,
    }


@router.get("/templates")
def templates(db: DbSession, user: CurrentUser) -> list[dict]:
    return icpc_service.template_library(db, user.id)


@router.get("/templates/{slug}")
def template(slug: str, db: DbSession, user: CurrentUser) -> dict:
    return icpc_service.get_template(db, user.id, slug)


@router.post("/templates/{slug}/review", status_code=201)
def review_template(
    slug: str, payload: TemplateReviewRequest, db: DbSession, user: CurrentUser
) -> dict:
    review = icpc_service.record_template_review(
        db,
        user.id,
        slug,
        from_memory=payload.from_memory,
        seconds_taken=payload.seconds_taken,
        confidence=payload.confidence,
    )
    return {
        "template_slug": review.template_slug,
        "reviewed_at": review.reviewed_at.isoformat(),
        "from_memory": review.from_memory,
    }


@router.get("/contests")
def contests(
    db: DbSession, user: CurrentUser, limit: int = Query(20, ge=1, le=100)
) -> list[dict]:
    return icpc_service.list_virtual_contests(db, user.id, limit)


@router.post("/contests", status_code=201)
def create_contest(
    payload: VirtualContestRequest, db: DbSession, user: CurrentUser
) -> dict:
    contest = icpc_service.create_virtual_contest(
        db,
        user.id,
        name=payload.name,
        problem_ids=[_uuid(pid, "problem_id") for pid in payload.problem_ids],
        duration_minutes=payload.duration_minutes,
    )
    return icpc_service.serialize_contest(contest)


@router.put("/contests/{contest_id}/problems/{problem_id}")
def update_contest_problem(
    contest_id: str,
    problem_id: str,
    payload: VirtualContestProblemRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    row = icpc_service.update_contest_problem(
        db,
        user.id,
        _uuid(contest_id, "contest_id"),
        _uuid(problem_id, "problem_id"),
        status=payload.status,
        wrong_attempts=payload.wrong_attempts,
        solved_at_minute=payload.solved_at_minute,
    )
    return {
        "problem_id": str(row.problem_id),
        "status": row.status,
        "wrong_attempts": row.wrong_attempts,
        "solved_at_minute": row.solved_at_minute,
    }


@router.post("/contests/{contest_id}/finish")
def finish_contest(
    contest_id: str, db: DbSession, user: CurrentUser, notes: str | None = None
) -> dict:
    return icpc_service.finish_virtual_contest(
        db, user.id, _uuid(contest_id, "contest_id"), notes=notes
    )


@router.get("/upsolve")
def upsolve_queue(
    db: DbSession, user: CurrentUser, limit: int = Query(20, ge=1, le=100)
) -> list[dict]:
    return icpc_service.unsolved_from_contests(db, user.id, limit)


@router.get("/readiness")
def readiness(db: DbSession, user: CurrentUser) -> dict:
    return icpc_service.compute_readiness(db, user.id, user.timezone)


@router.post("/readiness/snapshot", status_code=201)
def snapshot(db: DbSession, user: CurrentUser) -> dict:
    return icpc_service.snapshot_readiness(db, user.id, user.timezone)


@router.get("/readiness/trend")
def trend(
    db: DbSession, user: CurrentUser, days: int = Query(90, ge=7, le=365)
) -> list[dict]:
    return icpc_service.readiness_trend(db, user.id, days)
