"""Profile, settings, connected accounts and sync."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings as app_settings
from app.gamification.rules import build_level_table
from app.models.enums import MISTAKE_LABELS
from app.schemas.requests import (
    PlatformAccountRequest,
    ProfileUpdate,
    SettingsUpdate,
)
from app.services import user_service
from app.services.sync_service import sync_account, sync_all, sync_status

router = APIRouter(tags=["user"])


@router.get("/me")
def me(db: DbSession, user: CurrentUser) -> dict:
    config = user_service.get_settings_for(db, user.id)
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "timezone": user.timezone,
        "created_at": user.created_at.isoformat(),
        "settings": {
            "daily_goal": config.daily_goal,
            "weekly_goal": config.weekly_goal,
            "max_freezes": config.max_freezes,
            "freeze_cost_xp": config.freeze_cost_xp,
            "auto_apply_freeze": config.auto_apply_freeze,
            "ai_daily_insights": config.ai_daily_insights,
            "ai_weekly_reviews": config.ai_weekly_reviews,
            "ai_contest_analysis": config.ai_contest_analysis,
            "ai_recommendations": config.ai_recommendations,
            "ai_coach": config.ai_coach,
            "ai_daily_request_budget": config.ai_daily_request_budget,
            "ai_model_override": config.ai_model_override,
        },
        "accounts": sync_status(db, user.id),
        "ai_available": app_settings.ai_configured,
    }


@router.patch("/me")
def update_me(payload: ProfileUpdate, db: DbSession, user: CurrentUser) -> dict:
    updated = user_service.update_profile(
        db, user, **payload.model_dump(exclude_none=True)
    )
    return {
        "id": str(updated.id),
        "username": updated.username,
        "display_name": updated.display_name,
        "timezone": updated.timezone,
    }


@router.patch("/me/settings")
def update_settings(payload: SettingsUpdate, db: DbSession, user: CurrentUser) -> dict:
    config = user_service.update_settings(
        db, user.id, **payload.model_dump(exclude_none=True)
    )
    return {
        "daily_goal": config.daily_goal,
        "weekly_goal": config.weekly_goal,
        "max_freezes": config.max_freezes,
        "freeze_cost_xp": config.freeze_cost_xp,
        "auto_apply_freeze": config.auto_apply_freeze,
        "ai_coach": config.ai_coach,
        "ai_daily_request_budget": config.ai_daily_request_budget,
    }


@router.get("/me/accounts")
def accounts(db: DbSession, user: CurrentUser) -> list[dict]:
    return sync_status(db, user.id)


@router.post("/me/accounts")
def connect_account(
    payload: PlatformAccountRequest, db: DbSession, user: CurrentUser
) -> dict:
    account = user_service.upsert_platform_account(
        db, user.id, payload.platform, payload.username
    )
    return {
        "platform": account.platform,
        "username": account.username,
        "connected": account.connected,
    }


@router.delete("/me/accounts/{platform}")
def disconnect_account(platform: str, db: DbSession, user: CurrentUser) -> dict:
    user_service.disconnect_platform_account(db, user.id, platform)
    return {"disconnected": platform}


@router.post("/sync/{platform}")
def sync_platform(platform: str, db: DbSession, user: CurrentUser) -> dict:
    """Sync one platform.

    Returns 200 with `status: "failed"` when the upstream is unreachable —
    a sync failure is not a client error, and the dashboard stays usable.
    """
    return sync_account(db, user.id, platform).as_dict()


@router.post("/sync")
def sync_everything(db: DbSession, user: CurrentUser) -> dict:
    results = [result.as_dict() for result in sync_all(db, user.id)]
    return {"results": results, "synced": len(results)}


@router.get("/sync/status")
def status(db: DbSession, user: CurrentUser) -> list[dict]:
    return sync_status(db, user.id)


@router.get("/reference")
def reference() -> dict:
    """Static vocabularies the frontend renders in dropdowns."""
    return {
        "mistake_types": [
            {"value": value, "label": label} for value, label in MISTAKE_LABELS.items()
        ],
        "levels": build_level_table(),
        "solution_sources": [
            {"value": "independent", "label": "Solved independently"},
            {"value": "hint", "label": "Solved with a hint"},
            {"value": "editorial", "label": "Solved after the editorial"},
            {"value": "discussion", "label": "Solved after discussion"},
            {"value": "copied", "label": "Copied the implementation"},
        ],
        "statuses": [
            {"value": "unsolved", "label": "Unsolved"},
            {"value": "attempted", "label": "Attempted"},
            {"value": "solved", "label": "Solved"},
            {"value": "revisit", "label": "Revisit"},
            {"value": "mastered", "label": "Mastered"},
            {"value": "skipped", "label": "Skipped"},
        ],
    }
