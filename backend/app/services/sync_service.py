"""Platform sync.

Flow:

    Platform API -> normalize -> canonical problem (deduplicated)
                 -> submission (idempotent) -> solve -> aggregates

An unreachable platform is a normal condition. The sync records the failure,
leaves every existing row untouched, and reports when the last good sync was.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ExternalServiceError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations.base import IntegrationError
from app.integrations.codeforces import CodeforcesClient, ExternalSubmission
from app.integrations.leetcode import LeetCodeClient
from app.models.enums import (
    SYNCABLE_PLATFORMS,
    Platform,
    SolutionSource,
    SubmissionSource,
)
from app.models.progress import Submission
from app.models.recommendation import SyncRun
from app.models.user import PlatformAccount
from app.services.problem_service import get_or_create_problem
from app.services.solve_service import (
    record_attempt,
    record_solve,
    recompute_user_state,
)
from app.utils.timeutils import utcnow

log = get_logger(__name__)

#: How many submissions to pull per sync. Codeforces returns newest-first.
CODEFORCES_PAGE_SIZE = 2000


@dataclass
class SyncResult:
    platform: str
    status: str = "success"
    submissions_fetched: int = 0
    submissions_new: int = 0
    problems_created: int = 0
    problems_solved: int = 0
    xp_awarded: int = 0
    error: str | None = None
    last_success: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "status": self.status,
            "submissions_fetched": self.submissions_fetched,
            "submissions_new": self.submissions_new,
            "problems_created": self.problems_created,
            "problems_solved": self.problems_solved,
            "xp_awarded": self.xp_awarded,
            "error": self.error,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "details": self.details,
        }


def get_account(db: Session, user_id: uuid.UUID, platform: str) -> PlatformAccount:
    account = db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user_id, PlatformAccount.platform == platform
        )
    )
    if account is None:
        raise NotFoundError(
            f"No {platform} account is connected. Add your handle in Settings first."
        )
    return account


def last_successful_sync(
    db: Session, user_id: uuid.UUID, platform: str
) -> datetime | None:
    return db.scalar(
        select(SyncRun.finished_at)
        .where(
            SyncRun.user_id == user_id,
            SyncRun.platform == platform,
            SyncRun.status == "success",
        )
        .order_by(SyncRun.finished_at.desc())
        .limit(1)
    )


def sync_account(db: Session, user_id: uuid.UUID, platform: str) -> SyncResult:
    """Sync one platform account. Never raises for upstream outages."""
    platform = platform.strip().lower()
    if platform not in SYNCABLE_PLATFORMS:
        raise ValidationError(f"{platform!r} is not a syncable platform")

    account = get_account(db, user_id, platform)
    previous_success = last_successful_sync(db, user_id, platform)

    run = SyncRun(
        user_id=user_id, platform=platform, started_at=utcnow(), status="running"
    )
    db.add(run)
    db.commit()

    result = SyncResult(platform=platform, last_success=previous_success)

    try:
        if platform == Platform.CODEFORCES:
            submissions = _fetch_codeforces(account, result)
        else:
            submissions = _fetch_leetcode(account, result)
    except IntegrationError as exc:
        run.status = "failed"
        run.finished_at = utcnow()
        run.error = exc.message
        account.last_sync_status = "failed"
        account.last_sync_error = exc.message
        db.commit()

        log.warning("sync failed", platform=platform, error=exc.message)
        result.status = "failed"
        result.error = exc.message
        return result

    result.submissions_fetched = len(submissions)

    # Oldest first so "first solve" timestamps and the heatmap come out right.
    submissions.sort(key=lambda s: s.submitted_at)

    existing_ids = set(
        db.scalars(
            select(Submission.external_submission_id).where(
                Submission.user_id == user_id, Submission.platform == platform
            )
        ).all()
    )

    for submission in submissions:
        if submission.external_id in existing_ids:
            continue
        try:
            outcome = _ingest(db, user_id, submission)
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the sync
            log.warning(
                "failed to ingest submission",
                platform=platform,
                submission=submission.external_id,
                error=str(exc),
            )
            db.rollback()
            continue

        result.submissions_new += 1
        result.problems_created += outcome["problem_created"]
        result.problems_solved += outcome["solved"]
        result.xp_awarded += outcome["xp"]

    # One rebuild instead of one per submission.
    aggregates = recompute_user_state(db, user_id)
    result.details = {
        "streak": aggregates["streak"],
        "achievements_unlocked": aggregates["achievements_unlocked"],
        "handle": account.username,
    }

    _refresh_account_profile(account, platform, result)

    now = utcnow()
    account.last_synced_at = now
    account.last_sync_status = "success"
    account.last_sync_error = None
    run.status = "success"
    run.finished_at = now
    run.submissions_fetched = result.submissions_fetched
    run.submissions_new = result.submissions_new
    run.problems_created = result.problems_created
    run.problems_solved = result.problems_solved
    run.xp_awarded = result.xp_awarded
    run.details = result.details
    db.commit()

    result.last_success = now
    log.info(
        "sync complete",
        platform=platform,
        fetched=result.submissions_fetched,
        new=result.submissions_new,
        solved=result.problems_solved,
    )
    return result


def _fetch_codeforces(
    account: PlatformAccount, result: SyncResult
) -> list[ExternalSubmission]:
    client = CodeforcesClient()
    submissions = client.fetch_submissions(account.username, limit=CODEFORCES_PAGE_SIZE)
    try:
        info = client.fetch_user_info(account.username)
        if info:
            result.details["rating"] = info.get("rating")
            result.details["max_rating"] = info.get("max_rating")
            result.details["rank"] = info.get("rank")
    except IntegrationError:
        # Rating is a nice-to-have; submissions already succeeded.
        pass
    return submissions


def _fetch_leetcode(
    account: PlatformAccount, result: SyncResult
) -> list[ExternalSubmission]:
    client = LeetCodeClient()
    submissions = client.fetch_submissions(account.username, limit=20)
    try:
        info = client.fetch_user_info(account.username)
        if info:
            result.details["solved_counts"] = info.get("solved")
            result.details["ranking"] = info.get("ranking")
    except IntegrationError:
        pass

    result.details["note"] = (
        "LeetCode's public API exposes only the ~20 most recent accepted "
        "submissions. Sync regularly, or use scripts/import_leetcode.py to "
        "backfill full history from an export."
    )
    return submissions


def _ingest(
    db: Session, user_id: uuid.UUID, submission: ExternalSubmission
) -> dict[str, int]:
    metadata = submission.problem_metadata or {}
    problem, created = get_or_create_problem(
        db,
        submission.problem_ref,
        title=metadata.get("title"),
        rating=metadata.get("rating"),
        rating_source=submission.problem_ref.platform,
        tags=metadata.get("tags"),
        difficulty=metadata.get("difficulty"),
        commit=False,
    )

    if submission.is_accepted:
        outcome = record_solve(
            db,
            user_id,
            problem.id,
            solved_at=submission.submitted_at,
            external_submission_id=submission.external_id,
            submission_source=SubmissionSource.SYNC,
            during_contest=submission.during_contest,
            external_contest_id=submission.external_contest_id,
            language=submission.language,
            # A synced solve carries no self-report: we know it was accepted,
            # not how much help it took. Recording `unknown` keeps independence
            # statistics honest, and no session is created so solve-time stats
            # stay limited to sessions the user actually timed.
            solution_source=SolutionSource.UNKNOWN,
            create_session=False,
            defer_aggregates=True,
            commit=False,
        )
        db.commit()
        return {
            "problem_created": int(created),
            "solved": int(outcome.first_solve),
            "xp": outcome.xp_awarded,
        }

    record_attempt(
        db,
        user_id,
        problem.id,
        attempted_at=submission.submitted_at,
        verdict=submission.verdict,
        external_submission_id=submission.external_id,
        submission_source=SubmissionSource.SYNC,
        language=submission.language,
        commit=False,
    )
    db.commit()
    return {"problem_created": int(created), "solved": 0, "xp": 0}


def _refresh_account_profile(
    account: PlatformAccount, platform: str, result: SyncResult
) -> None:
    if platform == Platform.CODEFORCES:
        if result.details.get("rating") is not None:
            account.current_rating = result.details["rating"]
        if result.details.get("max_rating") is not None:
            account.max_rating = result.details["max_rating"]


def sync_all(db: Session, user_id: uuid.UUID) -> list[SyncResult]:
    accounts = db.scalars(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user_id, PlatformAccount.connected.is_(True)
        )
    ).all()
    return [sync_account(db, user_id, account.platform) for account in accounts]


def sync_status(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    accounts = db.scalars(
        select(PlatformAccount).where(PlatformAccount.user_id == user_id)
    ).all()
    return [
        {
            "platform": account.platform,
            "username": account.username,
            "connected": account.connected,
            "last_synced_at": account.last_synced_at.isoformat()
            if account.last_synced_at
            else None,
            "last_sync_status": account.last_sync_status,
            "last_sync_error": account.last_sync_error,
            "current_rating": account.current_rating,
            "max_rating": account.max_rating,
        }
        for account in accounts
    ]


def require_available(db: Session, user_id: uuid.UUID, platform: str) -> None:
    """Raise a user-readable 503 when a sync is attempted while down."""
    last = last_successful_sync(db, user_id, platform)
    raise ExternalServiceError(
        platform.title(),
        f"{platform.title()} sync is temporarily unavailable. Your existing data is safe.",
        last_success=last.isoformat() if last else None,
    )
