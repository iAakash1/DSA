"""Health and capability discovery.

The frontend calls `/api/health` on boot to learn which optional subsystems are
configured, so it can hide AI surfaces instead of rendering broken ones.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DbSession) -> dict:
    database_ok = True
    database_error: str | None = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        database_ok = False
        database_error = str(exc)

    return {
        "status": "ok" if database_ok else "degraded",
        "time": datetime.now(timezone.utc).isoformat(),
        "environment": settings.app_env,
        "database": {
            "ok": database_ok,
            "dialect": "postgresql" if settings.is_postgres else "sqlite",
            "error": database_error,
        },
        "features": {
            "auth_mode": settings.auth_mode,
            "supabase_configured": bool(settings.supabase_url),
            "ai_configured": settings.ai_configured,
            "ai_model": settings.groq_model if settings.ai_configured else None,
            "youtube_configured": settings.youtube_configured,
            "scheduler_enabled": settings.scheduler_enabled,
        },
    }
