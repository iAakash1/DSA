"""Dashboard, activity, recommendations, reviews and missions."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.analytics.activity import day_detail, heatmap, recent_activity, weekly_totals
from app.core.errors import ValidationError
from app.recommendations.engine import (
    dismiss_recommendation,
    get_recommendations,
    refresh_recommendations,
)
from app.schemas.requests import QueueReviewRequest, ReviewCompleteRequest
from app.services import review_service
from app.services.dashboard_service import build_dashboard
from app.services.mission_service import missions_for_today

router = APIRouter(tags=["practice"])


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"{field} must be a UUID") from exc


@router.get("/dashboard")
def dashboard(db: DbSession, user: CurrentUser) -> dict:
    return build_dashboard(db, user.id)


@router.get("/activity/heatmap")
def activity_heatmap(
    db: DbSession, user: CurrentUser, days: int = Query(365, ge=30, le=730)
) -> dict:
    return heatmap(db, user.id, user.timezone, days=days)


@router.get("/activity/day/{day}")
def activity_day(day: str, db: DbSession, user: CurrentUser) -> dict:
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise ValidationError("Date must be in YYYY-MM-DD format") from exc
    return day_detail(db, user.id, parsed, user.timezone)


@router.get("/activity/recent")
def activity_recent(
    db: DbSession, user: CurrentUser, limit: int = Query(15, ge=1, le=100)
) -> list[dict]:
    return recent_activity(db, user.id, limit)


@router.get("/activity/weekly")
def activity_weekly(
    db: DbSession, user: CurrentUser, weeks: int = Query(12, ge=1, le=52)
) -> list[dict]:
    return weekly_totals(db, user.id, user.timezone, weeks)


@router.get("/recommendations")
def recommendations(
    db: DbSession, user: CurrentUser, limit: int = Query(6, ge=1, le=20)
) -> list[dict]:
    return get_recommendations(db, user.id, limit=limit, tz=user.timezone)


@router.post("/recommendations/refresh")
def refresh(
    db: DbSession, user: CurrentUser, limit: int = Query(6, ge=1, le=20)
) -> list[dict]:
    return refresh_recommendations(db, user.id, limit=limit, tz=user.timezone)


@router.post("/recommendations/{recommendation_id}/dismiss")
def dismiss(recommendation_id: str, db: DbSession, user: CurrentUser) -> dict:
    dismiss_recommendation(db, user.id, _uuid(recommendation_id, "recommendation_id"))
    return {"dismissed": recommendation_id}


@router.get("/reviews")
def reviews(
    db: DbSession,
    user: CurrentUser,
    include_upcoming: bool = False,
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    due = review_service.get_due_reviews(
        db, user.id, limit=limit, include_upcoming=include_upcoming
    )
    return {
        "due_count": review_service.count_due(db, user.id),
        "items": [
            {
                "id": str(review.id),
                "problem_id": str(review.problem_id),
                "problem": {
                    "title": review.problem.title,
                    "platform": review.problem.platform,
                    "external_id": review.problem.external_id,
                    "url": review.problem.url,
                    "rating": review.problem.rating,
                    "difficulty": review.problem.difficulty,
                },
                "reason": review.reason,
                "reason_detail": review.reason_detail,
                "scheduled_for": review.scheduled_for.isoformat(),
                "interval_days": review.interval_days,
            }
            for review in due
        ],
    }


@router.post("/reviews/{review_id}/complete")
def complete_review(
    review_id: str,
    payload: ReviewCompleteRequest,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    review = review_service.complete_review(
        db, user.id, _uuid(review_id, "review_id"), payload.outcome
    )
    return {
        "id": str(review.id),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        "outcome": review.outcome,
        "due_count": review_service.count_due(db, user.id),
    }


@router.post("/reviews", status_code=201)
def queue_review(
    payload: QueueReviewRequest, db: DbSession, user: CurrentUser
) -> dict:
    review = review_service.queue_review(
        db,
        user.id,
        _uuid(payload.problem_id, "problem_id"),
        payload.reason,
        payload.interval_days,
    )
    return {
        "id": str(review.id),
        "scheduled_for": review.scheduled_for.isoformat(),
        "reason": review.reason,
    }


@router.get("/missions")
def missions(db: DbSession, user: CurrentUser) -> list[dict]:
    return missions_for_today(db, user.id, user.timezone)
