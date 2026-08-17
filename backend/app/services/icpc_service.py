"""ICPC mode: settings, countdown, roadmap, templates and virtual contests.

Readiness itself lives in `app.icpc.readiness` — this module is the write side
and the assembly of the dashboard payload.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.icpc.readiness import compute_readiness, roadmap_progress
from app.icpc.roadmap import NODES, PHASES
from app.icpc.templates import TEMPLATES_BY_SLUG, template_detail, template_summaries
from app.models.icpc import (
    ICPCSettings,
    ICPCTopicProgress,
    ReadinessSnapshot,
    TemplateReview,
    VirtualContest,
    VirtualContestProblem,
)
from app.models.problem import Problem
from app.services.problem_service import require_problem
from app.utils.timeutils import local_date, utcnow

#: A virtual contest longer than this is almost certainly an abandoned row.
MAX_CONTEST_MINUTES = 6 * 60

VALID_CONTEST_STATUSES = ("draft", "running", "finished", "abandoned")
VALID_PROBLEM_STATUSES = ("not_attempted", "attempted", "solved", "upsolved")


# ---------------------------------------------------------------------------
# Settings and countdown
# ---------------------------------------------------------------------------


def get_settings(db: Session, user_id: uuid.UUID) -> ICPCSettings | None:
    return db.get(ICPCSettings, user_id)


def update_settings(
    db: Session,
    user_id: uuid.UUID,
    *,
    target_date: date | None = None,
    team_name: str | None = None,
    weekly_practice_days: int | None = None,
    target_rating: int | None = None,
    focus_topics: list[str] | None = None,
    enabled: bool | None = None,
) -> ICPCSettings:
    settings = db.get(ICPCSettings, user_id)
    if settings is None:
        settings = ICPCSettings(user_id=user_id)
        try:
            with db.begin_nested():
                db.add(settings)
        except IntegrityError:
            settings = db.get(ICPCSettings, user_id)
            if settings is None:
                raise

    if target_date is not None:
        settings.target_date = target_date
    if team_name is not None:
        settings.team_name = team_name.strip() or None
    if weekly_practice_days is not None:
        if not 1 <= weekly_practice_days <= 7:
            raise ValidationError("Practice days per week must be between 1 and 7")
        settings.weekly_practice_days = weekly_practice_days
    if target_rating is not None:
        if not 800 <= target_rating <= 3500:
            raise ValidationError("Target rating must be between 800 and 3500")
        settings.target_rating = target_rating
    if focus_topics is not None:
        unknown = [key for key in focus_topics if key not in NODES]
        if unknown:
            raise ValidationError(f"Unknown roadmap topic(s): {', '.join(unknown)}")
        settings.focus_topics = focus_topics
    if enabled is not None:
        settings.enabled = enabled

    db.commit()
    return settings


def countdown(settings: ICPCSettings | None, tz: str | None) -> dict[str, Any]:
    """Days remaining, or an honest null when no date has been set."""
    if settings is None or settings.target_date is None:
        return {
            "target_date": None,
            "days_remaining": None,
            "weeks_remaining": None,
            "is_past": False,
            "message": "Set a contest date to start the countdown.",
        }
    today = local_date(utcnow(), tz)
    delta = (settings.target_date - today).days
    return {
        "target_date": settings.target_date.isoformat(),
        "days_remaining": max(delta, 0),
        "weeks_remaining": max(delta, 0) // 7,
        "is_past": delta < 0,
        "practice_days_remaining": (
            max(delta, 0) * (settings.weekly_practice_days / 7.0)
            if delta > 0
            else 0
        ),
        "message": None,
    }


# ---------------------------------------------------------------------------
# Roadmap
# ---------------------------------------------------------------------------


def set_topic_progress(
    db: Session,
    user_id: uuid.UUID,
    topic_key: str,
    *,
    studied: bool | None = None,
    template_reviewed: bool | None = None,
    confidence: int | None = None,
    notes: str | None = None,
) -> ICPCTopicProgress:
    if topic_key not in NODES:
        raise ValidationError(f"Unknown roadmap topic {topic_key!r}")
    if confidence is not None and not 1 <= confidence <= 5:
        raise ValidationError("Confidence must be between 1 and 5")

    row = db.scalar(
        select(ICPCTopicProgress).where(
            ICPCTopicProgress.user_id == user_id,
            ICPCTopicProgress.topic_key == topic_key,
        )
    )
    if row is None:
        row = ICPCTopicProgress(user_id=user_id, topic_key=topic_key)
        try:
            with db.begin_nested():
                db.add(row)
        except IntegrityError:
            row = db.scalar(
                select(ICPCTopicProgress).where(
                    ICPCTopicProgress.user_id == user_id,
                    ICPCTopicProgress.topic_key == topic_key,
                )
            )
            if row is None:
                raise

    if studied is not None:
        row.studied = studied
    if template_reviewed is not None:
        row.template_reviewed = template_reviewed
    if confidence is not None:
        row.confidence = confidence
    if notes is not None:
        row.notes = notes or None
    row.last_practiced_at = utcnow()

    db.commit()
    return row


def roadmap(db: Session, user_id: uuid.UUID, tz: str | None = None) -> dict[str, Any]:
    """The roadmap joined to solve evidence and the user's own study markers."""
    self_reported = {
        row.topic_key: row
        for row in db.scalars(
            select(ICPCTopicProgress).where(ICPCTopicProgress.user_id == user_id)
        )
    }
    nodes = roadmap_progress(db, user_id, tz)
    for node in nodes:
        marker = self_reported.get(node["key"])
        # Self-report and solve evidence are kept apart deliberately: ticking
        # "studied" is a note to yourself, not proof of anything.
        node["studied"] = bool(marker and marker.studied)
        node["template_reviewed"] = bool(marker and marker.template_reviewed)
        node["self_confidence"] = marker.confidence if marker else None
        node["notes"] = marker.notes if marker else None

    by_phase: dict[str, list[dict]] = {key: [] for key, _ in PHASES}
    for node in nodes:
        by_phase[node["phase"]].append(node)

    return {
        "phases": [
            {"key": key, "name": name, "nodes": by_phase[key]} for key, name in PHASES
        ],
        "totals": {
            "nodes": len(nodes),
            "comfortable": sum(1 for n in nodes if n["state"] == "comfortable"),
            "started": sum(1 for n in nodes if n["state"] == "started"),
            "ready": sum(1 for n in nodes if n["state"] == "ready"),
            "blocked": sum(1 for n in nodes if n["state"] == "blocked"),
        },
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def template_library(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The library, annotated with each template's own review history."""
    rows = db.execute(
        select(
            TemplateReview.template_slug,
            func.count(TemplateReview.id),
            func.max(TemplateReview.reviewed_at),
        )
        .where(TemplateReview.user_id == user_id)
        .group_by(TemplateReview.template_slug)
    ).all()
    memory_rows = db.execute(
        select(TemplateReview.template_slug)
        .where(TemplateReview.user_id == user_id, TemplateReview.from_memory.is_(True))
        .distinct()
    ).scalars().all()
    from_memory = set(memory_rows)
    history = {slug: (count, last) for slug, count, last in rows}

    library = template_summaries()
    for entry in library:
        count, last = history.get(entry["slug"], (0, None))
        entry["reviews"] = count
        entry["last_reviewed_at"] = last.isoformat() if last else None
        entry["typed_from_memory"] = entry["slug"] in from_memory
    return library


def record_template_review(
    db: Session,
    user_id: uuid.UUID,
    template_slug: str,
    *,
    from_memory: bool = False,
    seconds_taken: int | None = None,
    confidence: int | None = None,
) -> TemplateReview:
    if template_slug not in TEMPLATES_BY_SLUG:
        raise NotFoundError(f"No template named {template_slug!r}")
    if confidence is not None and not 1 <= confidence <= 5:
        raise ValidationError("Confidence must be between 1 and 5")
    if seconds_taken is not None and not 0 < seconds_taken <= 3600:
        raise ValidationError("Time taken must be between 1 second and one hour")

    review = TemplateReview(
        user_id=user_id,
        template_slug=template_slug,
        reviewed_at=utcnow(),
        from_memory=from_memory,
        seconds_taken=seconds_taken,
        confidence=confidence,
    )
    db.add(review)
    db.commit()
    return review


def get_template(db: Session, user_id: uuid.UUID, slug: str) -> dict[str, Any]:
    detail = template_detail(slug)
    if detail is None:
        raise NotFoundError(f"No template named {slug!r}")
    reviews = db.scalars(
        select(TemplateReview)
        .where(TemplateReview.user_id == user_id, TemplateReview.template_slug == slug)
        .order_by(TemplateReview.reviewed_at.desc())
        .limit(10)
    ).all()
    detail["reviews"] = [
        {
            "reviewed_at": r.reviewed_at.isoformat(),
            "from_memory": r.from_memory,
            "seconds_taken": r.seconds_taken,
            "confidence": r.confidence,
        }
        for r in reviews
    ]
    return detail


# ---------------------------------------------------------------------------
# Virtual contests
# ---------------------------------------------------------------------------


def create_virtual_contest(
    db: Session,
    user_id: uuid.UUID,
    *,
    name: str,
    problem_ids: list[uuid.UUID],
    duration_minutes: int = 180,
) -> VirtualContest:
    if not name.strip():
        raise ValidationError("A virtual contest needs a name")
    if not problem_ids:
        raise ValidationError("A virtual contest needs at least one problem")
    if not 0 < duration_minutes <= MAX_CONTEST_MINUTES:
        raise ValidationError(
            f"Duration must be between 1 and {MAX_CONTEST_MINUTES} minutes"
        )
    if len(set(problem_ids)) != len(problem_ids):
        raise ValidationError("The same problem cannot appear twice in one contest")

    contest = VirtualContest(
        user_id=user_id,
        name=name.strip(),
        duration_minutes=duration_minutes,
        started_at=utcnow(),
        status="running",
    )
    db.add(contest)
    db.flush()

    for position, problem_id in enumerate(problem_ids):
        require_problem(db, problem_id)  # 404s rather than storing a dangling id
        db.add(
            VirtualContestProblem(
                contest_id=contest.id,
                problem_id=problem_id,
                position=position,
                label=chr(ord("A") + position) if position < 26 else str(position + 1),
            )
        )
    db.commit()
    return contest


def _require_contest(
    db: Session, user_id: uuid.UUID, contest_id: uuid.UUID
) -> VirtualContest:
    contest = db.scalar(
        select(VirtualContest).where(
            VirtualContest.id == contest_id, VirtualContest.user_id == user_id
        )
    )
    if contest is None:
        raise NotFoundError("Virtual contest not found")
    return contest


def update_contest_problem(
    db: Session,
    user_id: uuid.UUID,
    contest_id: uuid.UUID,
    problem_id: uuid.UUID,
    *,
    status: str | None = None,
    wrong_attempts: int | None = None,
    solved_at_minute: int | None = None,
) -> VirtualContestProblem:
    contest = _require_contest(db, user_id, contest_id)
    row = db.scalar(
        select(VirtualContestProblem).where(
            VirtualContestProblem.contest_id == contest.id,
            VirtualContestProblem.problem_id == problem_id,
        )
    )
    if row is None:
        raise NotFoundError("That problem is not in this contest")

    if status is not None:
        if status not in VALID_PROBLEM_STATUSES:
            raise ValidationError(f"Unknown status {status!r}")
        row.status = status
        if status == "upsolved":
            row.upsolved_at = utcnow()
    if wrong_attempts is not None:
        if wrong_attempts < 0:
            raise ValidationError("Wrong attempts cannot be negative")
        row.wrong_attempts = wrong_attempts
    if solved_at_minute is not None:
        if not 0 <= solved_at_minute <= contest.duration_minutes:
            raise ValidationError(
                "Solve time must fall within the contest duration"
            )
        row.solved_at_minute = solved_at_minute

    db.commit()
    return row


def finish_virtual_contest(
    db: Session, user_id: uuid.UUID, contest_id: uuid.UUID, *, notes: str | None = None
) -> dict[str, Any]:
    contest = _require_contest(db, user_id, contest_id)
    contest.status = "finished"
    contest.finished_at = utcnow()
    if notes is not None:
        contest.notes = notes or None

    # ICPC penalty: 20 minutes per wrong attempt on a problem eventually solved.
    penalty = 0
    for row in contest.problems:
        if row.status in ("solved", "upsolved") and row.solved_at_minute is not None:
            penalty += row.solved_at_minute + 20 * row.wrong_attempts
    contest.penalty_minutes = penalty

    db.commit()
    return serialize_contest(contest)


def serialize_contest(contest: VirtualContest) -> dict[str, Any]:
    solved = [p for p in contest.problems if p.status == "solved"]
    return {
        "id": str(contest.id),
        "name": contest.name,
        "status": contest.status,
        "duration_minutes": contest.duration_minutes,
        "started_at": contest.started_at.isoformat(),
        "finished_at": contest.finished_at.isoformat() if contest.finished_at else None,
        "penalty_minutes": contest.penalty_minutes,
        "notes": contest.notes,
        "solved_count": len(solved),
        "problem_count": len(contest.problems),
        "problems": [
            {
                "problem_id": str(p.problem_id),
                "label": p.label,
                "position": p.position,
                "status": p.status,
                "wrong_attempts": p.wrong_attempts,
                "solved_at_minute": p.solved_at_minute,
                "upsolved_at": p.upsolved_at.isoformat() if p.upsolved_at else None,
                "title": p.problem.title if p.problem else None,
                "url": p.problem.url if p.problem else None,
                "rating": p.problem.rating if p.problem else None,
                "platform": p.problem.platform if p.problem else None,
            }
            for p in contest.problems
        ],
    }


def list_virtual_contests(
    db: Session, user_id: uuid.UUID, limit: int = 20
) -> list[dict[str, Any]]:
    contests = db.scalars(
        select(VirtualContest)
        .where(VirtualContest.user_id == user_id)
        .order_by(VirtualContest.started_at.desc())
        .limit(limit)
    ).all()
    return [serialize_contest(c) for c in contests]


def unsolved_from_contests(
    db: Session, user_id: uuid.UUID, limit: int = 20
) -> list[dict[str, Any]]:
    """The upsolve queue: problems a virtual contest left unsolved."""
    rows = db.execute(
        select(VirtualContestProblem, VirtualContest, Problem)
        .join(VirtualContest, VirtualContest.id == VirtualContestProblem.contest_id)
        .join(Problem, Problem.id == VirtualContestProblem.problem_id)
        .where(
            VirtualContest.user_id == user_id,
            VirtualContest.status == "finished",
            VirtualContestProblem.status.in_(("not_attempted", "attempted")),
        )
        .order_by(VirtualContest.started_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "problem_id": str(problem.id),
            "title": problem.title,
            "url": problem.url,
            "rating": problem.rating,
            "platform": problem.platform,
            "contest_id": str(contest.id),
            "contest_name": contest.name,
            "label": link.label,
            "wrong_attempts": link.wrong_attempts,
            "status": link.status,
        }
        for link, contest, problem in rows
    ]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def snapshot_readiness(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> dict[str, Any]:
    """Compute readiness and keep it, so the trend line is real history."""
    result = compute_readiness(db, user_id, tz)
    db.add(
        ReadinessSnapshot(
            user_id=user_id,
            taken_at=utcnow(),
            overall=result["overall"],
            components=result["components"],
            has_sufficient_data=result["has_sufficient_data"],
        )
    )
    db.commit()
    return result


def readiness_trend(
    db: Session, user_id: uuid.UUID, days: int = 90
) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(days=days)
    rows = db.scalars(
        select(ReadinessSnapshot)
        .where(
            ReadinessSnapshot.user_id == user_id,
            ReadinessSnapshot.taken_at >= since,
        )
        .order_by(ReadinessSnapshot.taken_at)
    ).all()
    return [
        {
            "taken_at": r.taken_at.isoformat(),
            "overall": r.overall,
            "has_sufficient_data": r.has_sufficient_data,
        }
        for r in rows
    ]


def dashboard(db: Session, user_id: uuid.UUID, tz: str | None = None) -> dict[str, Any]:
    settings = get_settings(db, user_id)
    return {
        "settings": {
            "target_date": settings.target_date.isoformat()
            if settings and settings.target_date
            else None,
            "team_name": settings.team_name if settings else None,
            "weekly_practice_days": settings.weekly_practice_days if settings else 5,
            "target_rating": settings.target_rating if settings else None,
            "focus_topics": (settings.focus_topics if settings else None) or [],
            "enabled": settings.enabled if settings else False,
            "configured": settings is not None,
        },
        "countdown": countdown(settings, tz),
        "readiness": compute_readiness(db, user_id, tz),
        "roadmap": roadmap(db, user_id, tz),
        "recent_contests": list_virtual_contests(db, user_id, limit=5),
        "upsolve_queue": unsolved_from_contests(db, user_id, limit=10),
    }
