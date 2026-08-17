"""Statistics, mastery, weaknesses and progression."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.analytics.mastery import pattern_mastery, topic_mastery, untouched_topics
from app.analytics.stats import (
    difficulty_progression,
    mistake_distribution,
    overview,
    solve_time_by_topic,
    submission_stats,
)
from app.analytics.weakness import weakness_summary
from app.api.deps import CurrentUser, DbSession

router = APIRouter(prefix="/stats", tags=["analytics"])


@router.get("")
def stats_overview(db: DbSession, user: CurrentUser) -> dict:
    return {
        **overview(db, user.id, user.timezone),
        "submissions": submission_stats(db, user.id),
    }


@router.get("/topics")
def topics(
    db: DbSession, user: CurrentUser, limit: int = Query(60, ge=1, le=200)
) -> dict:
    mastery = topic_mastery(db, user.id, user.timezone)
    return {
        "items": [m.as_dict() for m in mastery[:limit]],
        "untouched": untouched_topics(db, user.id),
    }


@router.get("/patterns")
def patterns(
    db: DbSession, user: CurrentUser, limit: int = Query(60, ge=1, le=200)
) -> dict:
    return {
        "items": [m.as_dict() for m in pattern_mastery(db, user.id, user.timezone)[:limit]]
    }


@router.get("/weaknesses")
def weaknesses(db: DbSession, user: CurrentUser) -> dict:
    return weakness_summary(db, user.id, user.timezone)


@router.get("/difficulty")
def difficulty(
    db: DbSession, user: CurrentUser, months: int = Query(12, ge=1, le=36)
) -> dict:
    return difficulty_progression(db, user.id, months)


@router.get("/mistakes")
def mistakes(db: DbSession, user: CurrentUser) -> dict:
    return mistake_distribution(db, user.id)


@router.get("/time")
def solve_time(db: DbSession, user: CurrentUser) -> dict:
    summary = overview(db, user.id, user.timezone)
    return {
        "summary": summary["time"],
        "by_topic": solve_time_by_topic(db, user.id, user.timezone),
    }
