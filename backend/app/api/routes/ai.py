"""AI Coach endpoints.

The frontend never talks to Groq. Every request goes through here so the API
key stays server-side and every call is scoped to the authenticated user.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.ai.service import AIService
from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import ValidationError
from app.models.enums import AIInsightType
from app.schemas.requests import AIChatRequest

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def status(db: DbSession, user: CurrentUser) -> dict:
    return AIService(db).status(user.id)


@router.get("/models")
def models(db: DbSession, user: CurrentUser) -> dict:
    """Live provider catalog, so the settings UI never offers a dead model."""
    service = AIService(db)
    return {
        "configured": service.available,
        "current": service.status(user.id)["model"],
        "available": service.provider.list_models(),
        "routing": {
            "default": settings.groq_model,
            "fast": settings.groq_model_fast,
            "strong": settings.groq_model_strong,
        },
    }


@router.get("/daily")
def daily(db: DbSession, user: CurrentUser, force: bool = False) -> dict:
    return AIService(db).get_or_generate(
        user.id, AIInsightType.DAILY_INSIGHT, force=force
    )


@router.get("/weekly")
def weekly(db: DbSession, user: CurrentUser, force: bool = False) -> dict:
    return AIService(db).get_or_generate(
        user.id, AIInsightType.WEEKLY_REVIEW, force=force
    )


@router.get("/weaknesses")
def weaknesses(db: DbSession, user: CurrentUser, force: bool = False) -> dict:
    return AIService(db).get_or_generate(
        user.id, AIInsightType.WEAKNESS_ANALYSIS, force=force
    )


@router.get("/progress")
def progress(db: DbSession, user: CurrentUser, force: bool = False) -> dict:
    return AIService(db).get_or_generate(
        user.id, AIInsightType.PROGRESS_ANALYSIS, force=force
    )


@router.get("/mistakes")
def mistakes(db: DbSession, user: CurrentUser, force: bool = False) -> dict:
    return AIService(db).get_or_generate(
        user.id, AIInsightType.MISTAKE_ANALYSIS, force=force
    )


@router.get("/study-plan")
def study_plan(
    db: DbSession,
    user: CurrentUser,
    force: bool = False,
    available_days: int = Query(7, ge=1, le=7),
) -> dict:
    from app.ai.context.builder import AIContextBuilder

    context = AIContextBuilder(db, user.id).study_plan(available_days=available_days)
    return AIService(db).get_or_generate(
        user.id, AIInsightType.STUDY_PLAN, force=force, context_override=context
    )


@router.get("/contest/{contest_id}")
def contest_analysis(
    contest_id: str, db: DbSession, user: CurrentUser, force: bool = False
) -> dict:
    from app.ai.context.builder import AIContextBuilder
    from app.services.contest_service import contest_history, contest_summary

    try:
        subject = uuid.UUID(contest_id)
    except ValueError as exc:
        raise ValidationError("contest_id must be a UUID") from exc

    history = contest_history(db, user.id, limit=10)
    target = next((c for c in history if c["contest_id"] == contest_id), None)
    if target is None:
        raise ValidationError("No recorded participation for that contest")

    builder = AIContextBuilder(db, user.id)
    context = {
        "contest": target,
        "previous_contests": [c for c in history if c["contest_id"] != contest_id][:5],
        "contest_summary": contest_summary(db, user.id),
        "weak_topics": builder.weak_topics(4),
        "difficulty": builder.difficulty(),
    }
    return AIService(db).get_or_generate(
        user.id,
        AIInsightType.CONTEST_ANALYSIS,
        force=force,
        context_override=context,
        subject_id=subject,
    )


@router.post("/chat")
def chat(payload: AIChatRequest, db: DbSession, user: CurrentUser) -> dict:
    conversation_id = None
    if payload.conversation_id:
        try:
            conversation_id = uuid.UUID(payload.conversation_id)
        except ValueError as exc:
            raise ValidationError("conversation_id must be a UUID") from exc

    return AIService(db).chat(user.id, payload.message, conversation_id)


@router.post("/refresh")
def refresh(db: DbSession, user: CurrentUser) -> dict:
    """Force-regenerate the daily insight."""
    return AIService(db).get_or_generate(
        user.id, AIInsightType.DAILY_INSIGHT, force=True
    )


@router.get("/usage")
def usage(db: DbSession, user: CurrentUser) -> dict:
    return AIService(db).usage(user.id)
