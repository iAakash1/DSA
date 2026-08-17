"""Contest tracking and upsolving.

Contests are a separate axis from the problem sheets. CodeChef appears here as
a contest platform only — it is never a CP-31/Striver problem source.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.integrations.base import IntegrationError
from app.integrations.codeforces import CodeforcesClient
from app.models.contest import (
    Contest,
    ContestParticipation,
    ContestProblemResult,
)
from app.models.enums import ContestSolveStatus, XPKind
from app.models.user import PlatformAccount
from app.utils.timeutils import local_date, utcnow

log = get_logger(__name__)


def upsert_contest(
    db: Session,
    platform: str,
    external_id: str,
    name: str,
    *,
    start_time=None,
    duration_seconds: int | None = None,
    url: str | None = None,
) -> Contest:
    contest = db.scalar(
        select(Contest).where(
            Contest.platform == platform, Contest.external_id == str(external_id)
        )
    )
    if contest is None:
        contest = Contest(
            platform=platform,
            external_id=str(external_id),
            name=name,
            start_time=start_time,
            duration_seconds=duration_seconds,
            url=url,
        )
        db.add(contest)
        db.flush()
    else:
        contest.name = name or contest.name
        contest.start_time = start_time or contest.start_time
        contest.duration_seconds = duration_seconds or contest.duration_seconds
    return contest


def record_participation(
    db: Session, user_id: uuid.UUID, payload: dict[str, Any]
) -> ContestParticipation:
    """Record a contest result, awarding participation XP once."""
    from app.gamification.streaks import record_activity, user_timezone
    from app.gamification.xp import award_xp, bonus_key, rules_for

    contest = upsert_contest(
        db,
        payload["platform"],
        payload["external_id"],
        payload["name"],
        start_time=payload.get("start_time"),
        duration_seconds=payload.get("duration_seconds"),
    )

    participation = db.scalar(
        select(ContestParticipation).where(
            ContestParticipation.user_id == user_id,
            ContestParticipation.contest_id == contest.id,
            ContestParticipation.is_virtual == payload.get("is_virtual", False),
        )
    )
    if participation is None:
        participation = ContestParticipation(
            user_id=user_id,
            contest_id=contest.id,
            is_virtual=payload.get("is_virtual", False),
        )
        db.add(participation)

    participation.rank = payload.get("rank", participation.rank)
    participation.rating_before = payload.get("rating_before", participation.rating_before)
    participation.rating_after = payload.get("rating_after", participation.rating_after)
    if participation.rating_before is not None and participation.rating_after is not None:
        participation.rating_change = participation.rating_after - participation.rating_before
    participation.problems_solved_live = payload.get(
        "problems_solved_live", participation.problems_solved_live
    )
    participation.penalty = payload.get("penalty", participation.penalty)
    participation.notes = payload.get("notes", participation.notes)
    db.flush()

    tz = user_timezone(db, user_id)
    when = contest.start_time or utcnow()
    day = local_date(when, tz)

    record_activity(db, user_id, day, contests=1)
    rules = rules_for(db, user_id)
    award_xp(
        db,
        user_id,
        amount=rules.bonus_for("contest_participation"),
        kind=XPKind.BONUS,
        reason=f"Contest: {contest.name}",
        dedupe_key=bonus_key("contest", str(contest.id)),
        activity_date=day,
    )

    db.commit()
    db.refresh(participation)
    return participation


def set_problem_result(
    db: Session,
    user_id: uuid.UUID,
    contest_id: uuid.UUID,
    problem_id: uuid.UUID,
    status: str,
) -> ContestProblemResult:
    """Mark a contest problem as solved live, upsolved, attempted or skipped."""
    from app.gamification.streaks import record_activity, user_timezone
    from app.gamification.xp import award_xp, bonus_key, rules_for

    result = db.scalar(
        select(ContestProblemResult).where(
            ContestProblemResult.user_id == user_id,
            ContestProblemResult.contest_id == contest_id,
            ContestProblemResult.problem_id == problem_id,
        )
    )
    if result is None:
        result = ContestProblemResult(
            user_id=user_id,
            contest_id=contest_id,
            problem_id=problem_id,
            status=status,
        )
        db.add(result)
    else:
        result.status = status

    if status in (ContestSolveStatus.LIVE, ContestSolveStatus.UPSOLVED):
        result.solved_at = result.solved_at or utcnow()

    db.flush()
    _refresh_counts(db, user_id, contest_id)

    if status == ContestSolveStatus.UPSOLVED:
        tz = user_timezone(db, user_id)
        day = local_date(utcnow(), tz)
        record_activity(db, user_id, day, upsolves=1)
        rules = rules_for(db, user_id)
        award_xp(
            db,
            user_id,
            amount=rules.bonus_for("upsolve"),
            kind=XPKind.BONUS,
            reason="Upsolved a contest problem",
            dedupe_key=bonus_key("upsolve", str(problem_id)),
            activity_date=day,
        )

    db.commit()
    db.refresh(result)
    return result


def _refresh_counts(db: Session, user_id: uuid.UUID, contest_id: uuid.UUID) -> None:
    rows = db.execute(
        select(ContestProblemResult.status, func.count(ContestProblemResult.id))
        .where(
            ContestProblemResult.user_id == user_id,
            ContestProblemResult.contest_id == contest_id,
        )
        .group_by(ContestProblemResult.status)
    ).all()
    counts = {status: int(count) for status, count in rows}

    participation = db.scalar(
        select(ContestParticipation).where(
            ContestParticipation.user_id == user_id,
            ContestParticipation.contest_id == contest_id,
        )
    )
    if participation is not None:
        participation.problems_solved_live = counts.get(ContestSolveStatus.LIVE, 0)
        participation.problems_upsolved = counts.get(ContestSolveStatus.UPSOLVED, 0)
        participation.problems_attempted = sum(counts.values())
        db.flush()


def contest_history(
    db: Session, user_id: uuid.UUID, limit: int = 20
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ContestParticipation, Contest)
        .join(Contest, Contest.id == ContestParticipation.contest_id)
        .where(ContestParticipation.user_id == user_id)
        .order_by(Contest.start_time.desc().nullslast())
        .limit(limit)
    ).all()

    return [
        {
            "id": str(participation.id),
            "contest_id": str(contest.id),
            "name": contest.name,
            "platform": contest.platform,
            "date": contest.start_time.isoformat() if contest.start_time else None,
            "rank": participation.rank,
            "rating_before": participation.rating_before,
            "rating_after": participation.rating_after,
            "rating_change": participation.rating_change,
            "solved_live": participation.problems_solved_live,
            "upsolved": participation.problems_upsolved,
            "total_solved": participation.problems_solved_live
            + participation.problems_upsolved,
            "is_virtual": participation.is_virtual,
            "notes": participation.notes,
        }
        for participation, contest in rows
    ]


def contest_summary(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    history = contest_history(db, user_id, limit=200)
    if not history:
        return {
            "count": 0,
            "best_rank": None,
            "current_rating": None,
            "max_rating": None,
            "total_live_solves": 0,
            "total_upsolves": 0,
            "average_solved_per_contest": 0.0,
            "rating_history": [],
            "recent": [],
        }

    ranks = [h["rank"] for h in history if h["rank"]]
    rated = [h for h in history if h["rating_after"] is not None]
    live = sum(h["solved_live"] for h in history)
    upsolved = sum(h["upsolved"] for h in history)

    return {
        "count": len(history),
        "best_rank": min(ranks) if ranks else None,
        "current_rating": rated[0]["rating_after"] if rated else None,
        "max_rating": max((h["rating_after"] for h in rated), default=None),
        "total_live_solves": live,
        "total_upsolves": upsolved,
        "average_solved_per_contest": round((live + upsolved) / len(history), 2),
        "rating_history": [
            {
                "date": h["date"],
                "rating": h["rating_after"],
                "change": h["rating_change"],
                "name": h["name"],
            }
            for h in reversed(rated)
        ],
        "recent": history[:10],
    }


def sync_codeforces_contests(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Import rated contest history from the Codeforces API."""
    account = db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user_id,
            PlatformAccount.platform == "codeforces",
        )
    )
    if account is None:
        raise NotFoundError("Connect your Codeforces handle first")

    try:
        history = CodeforcesClient().fetch_rating_history(account.username)
    except IntegrationError as exc:
        return {"status": "failed", "error": exc.message, "imported": 0}

    imported = 0
    for entry in history:
        contest = upsert_contest(
            db,
            "codeforces",
            entry["contest_id"],
            entry["contest_name"],
            start_time=entry["at"],
        )
        participation = db.scalar(
            select(ContestParticipation).where(
                ContestParticipation.user_id == user_id,
                ContestParticipation.contest_id == contest.id,
                ContestParticipation.is_virtual.is_(False),
            )
        )
        if participation is None:
            participation = ContestParticipation(
                user_id=user_id, contest_id=contest.id, is_virtual=False
            )
            db.add(participation)
            imported += 1
        participation.rank = entry["rank"]
        participation.rating_before = entry["rating_before"]
        participation.rating_after = entry["rating_after"]
        participation.rating_change = entry["rating_change"]

    db.commit()
    log.info("codeforces contests synced", user_id=str(user_id), imported=imported)
    return {"status": "success", "imported": imported, "total": len(history)}
