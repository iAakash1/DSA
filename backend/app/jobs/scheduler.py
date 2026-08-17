"""Background jobs.

APScheduler in-process — no Redis, no broker. This is a local-first application
and a distributed queue would be pure overhead.

Jobs are best-effort: a failure is logged and the next tick tries again. Nothing
in the request path depends on them having run.
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.user import PlatformAccount, Profile

log = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def sync_all_accounts() -> None:
    """Refresh every connected platform account."""
    from app.services.sync_service import sync_account

    with session_scope() as db:
        accounts = list(
            db.scalars(
                select(PlatformAccount).where(PlatformAccount.connected.is_(True))
            ).all()
        )

    for account in accounts:
        try:
            with session_scope() as db:
                result = sync_account(db, account.user_id, account.platform)
                log.info(
                    "scheduled sync finished",
                    platform=account.platform,
                    user_id=str(account.user_id),
                    new_submissions=result.submissions_new,
                )
        except Exception as exc:  # noqa: BLE001 - a job must never kill the loop
            log.warning(
                "scheduled sync failed",
                platform=account.platform,
                user_id=str(account.user_id),
                error=str(exc),
            )


def refresh_daily_state() -> None:
    """Roll streaks over, generate missions, refresh recommendations.

    Runs hourly rather than at a fixed hour because users live in different
    timezones; each user's own local day boundary is what matters and the
    underlying operations are idempotent per (user, date).
    """
    from app.gamification.streaks import roll_over_streak
    from app.recommendations.engine import refresh_recommendations
    from app.services.mission_service import ensure_missions_for_today

    with session_scope() as db:
        user_ids = list(db.scalars(select(Profile.id)).all())

    for user_id in user_ids:
        try:
            with session_scope() as db:
                roll_over_streak(db, user_id)
                ensure_missions_for_today(db, user_id)
                refresh_recommendations(db, user_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("daily refresh failed", user_id=str(user_id), error=str(exc))


def generate_daily_insights() -> None:
    """Pre-generate the AI daily briefing so the dashboard loads instantly.

    Silently skipped when AI is not configured.
    """
    if not settings.ai_configured:
        return

    from app.ai.service import AIService
    from app.models.enums import AIInsightType

    with session_scope() as db:
        user_ids = list(db.scalars(select(Profile.id)).all())

    for user_id in user_ids:
        try:
            with session_scope() as db:
                AIService(db).get_or_generate(user_id, AIInsightType.DAILY_INSIGHT)
        except Exception as exc:  # noqa: BLE001
            log.warning("daily insight failed", user_id=str(user_id), error=str(exc))


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.scheduler_enabled:
        log.info("scheduler disabled", hint="set SCHEDULER_ENABLED=true to enable")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        sync_all_accounts,
        IntervalTrigger(minutes=settings.sync_interval_minutes),
        id="sync_accounts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_daily_state,
        CronTrigger(minute=5),
        id="daily_state",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        generate_daily_insights,
        CronTrigger(hour="*/6", minute=15),
        id="daily_insights",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info("scheduler started", jobs=[j.id for j in scheduler.get_jobs()])
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
