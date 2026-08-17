"""Daily missions.

Missions are generated from the user's real state — weakest topic, current
CP-31 bucket, review backlog, demonstrated rating. A mission that ignores your
data ("solve a random hard problem!") is noise, so none are generated.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import SOLVED_STATUSES
from app.analytics.stats import comfortable_rating
from app.analytics.weakness import detect_weaknesses
from app.core.logging import get_logger
from app.models.enums import XPKind
from app.models.gamification import ActivityDay, DailyMission
from app.models.problem import Problem, ProblemTopic, Topic
from app.models.progress import UserProblem
from app.models.sheet import Sheet, SheetProblem, SheetSection
from app.models.user import UserSettings
from app.gamification.streaks import user_timezone
from app.gamification.xp import award_xp, bonus_key, rules_for
from app.utils.timeutils import local_date, today_in, utcnow

log = get_logger(__name__)

MAX_MISSIONS_PER_DAY = 4


def ensure_missions_for_today(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> list[DailyMission]:
    """Generate today's missions once. Idempotent per (user, date, code)."""
    tz = tz or user_timezone(db, user_id)
    today = today_in(tz)

    existing = list(
        db.scalars(
            select(DailyMission).where(
                DailyMission.user_id == user_id, DailyMission.mission_date == today
            )
        ).all()
    )
    if existing:
        _sync_progress(db, user_id, today, existing)
        return existing

    specs = _build_specs(db, user_id, tz, today)
    created: list[DailyMission] = []
    for spec in specs[:MAX_MISSIONS_PER_DAY]:
        mission = DailyMission(
            user_id=user_id,
            mission_date=today,
            code=spec["code"],
            title=spec["title"],
            description=spec["description"],
            target=spec.get("target", 1),
            xp_reward=spec.get("xp_reward", 25),
            params=spec.get("params"),
        )
        db.add(mission)
        created.append(mission)

    db.commit()
    _sync_progress(db, user_id, today, created)
    log.info("missions generated", user_id=str(user_id), count=len(created))
    return created


def _build_specs(
    db: Session, user_id: uuid.UUID, tz: str, today: date
) -> list[dict[str, Any]]:
    from app.services.review_service import count_due

    config = db.get(UserSettings, user_id)
    daily_goal = config.daily_goal if config else 2
    specs: list[dict[str, Any]] = [
        {
            "code": "daily_goal",
            "title": f"Solve {daily_goal} problem{'s' if daily_goal != 1 else ''}",
            "description": "Your daily baseline. Consistency beats intensity.",
            "target": daily_goal,
            "xp_reward": 25,
            "params": {"kind": "any"},
        }
    ]

    weaknesses = detect_weaknesses(db, user_id, tz, limit=3, include_patterns=False)
    if weaknesses:
        weakest = weaknesses[0]
        specs.append(
            {
                "code": f"weak_topic:{weakest.slug}",
                "title": f"Solve 1 {weakest.name} problem",
                "description": (
                    f"{weakest.name} is at {weakest.mastery:.0f}% mastery — "
                    f"{weakest.root_cause_label.lower()}."
                ),
                "target": 1,
                "xp_reward": 40,
                "params": {"kind": "topic", "topic": weakest.slug},
            }
        )

    bucket = _current_cp31_bucket(db, user_id)
    if bucket is not None:
        specs.append(
            {
                "code": f"cp31:{bucket}",
                "title": f"Clear 1 CP-31 problem from the {bucket} bucket",
                "description": "Keep the ladder moving.",
                "target": 1,
                "xp_reward": 35,
                "params": {"kind": "cp31_bucket", "bucket": bucket},
            }
        )

    due = count_due(db, user_id)
    if due:
        specs.append(
            {
                "code": "review",
                "title": f"Review {min(3, due)} problem{'s' if min(3, due) != 1 else ''}",
                "description": "Retention compounds. These are due today.",
                "target": min(3, due),
                "xp_reward": 30,
                "params": {"kind": "review"},
            }
        )

    comfort = comfortable_rating(db, user_id)
    if comfort and len(specs) < MAX_MISSIONS_PER_DAY:
        stretch = comfort + 100
        specs.append(
            {
                "code": f"rating_step:{stretch}",
                "title": f"Solve 1 problem rated {stretch}+",
                "description": (
                    f"You are reliable at {comfort}. One step up is how the "
                    "ceiling moves."
                ),
                "target": 1,
                "xp_reward": 50,
                "params": {"kind": "min_rating", "min_rating": stretch},
            }
        )

    return specs


def _current_cp31_bucket(db: Session, user_id: uuid.UUID) -> int | None:
    """The lowest CP-31 bucket that still has unsolved problems."""
    sheet = db.scalar(select(Sheet).where(Sheet.slug == "cp31"))
    if sheet is None:
        return None

    rows = db.execute(
        select(SheetSection.rating_bucket, func.count(SheetProblem.id))
        .select_from(SheetProblem)
        .join(SheetSection, SheetSection.id == SheetProblem.section_id)
        .outerjoin(
            UserProblem,
            (UserProblem.problem_id == SheetProblem.problem_id)
            & (UserProblem.user_id == user_id),
        )
        .where(
            SheetProblem.sheet_id == sheet.id,
            SheetSection.rating_bucket.is_not(None),
            (UserProblem.status.is_(None))
            | (UserProblem.status.not_in(SOLVED_STATUSES)),
        )
        .group_by(SheetSection.rating_bucket)
        .order_by(SheetSection.rating_bucket)
    ).all()

    for bucket, remaining in rows:
        if remaining:
            return int(bucket)
    return None


def update_mission_progress(
    db: Session, user_id: uuid.UUID, problem: Problem, day: date
) -> dict[str, int]:
    """Advance today's missions after a solve. Returns XP awarded per mission."""
    missions = list(
        db.scalars(
            select(DailyMission).where(
                DailyMission.user_id == user_id,
                DailyMission.mission_date == day,
                DailyMission.completed_at.is_(None),
            )
        ).all()
    )
    if not missions:
        return {}

    rules = rules_for(db, user_id)
    awarded: dict[str, int] = {}

    for mission in missions:
        params = mission.params or {}
        if not _matches(db, user_id, problem, params):
            continue

        mission.progress += 1
        if mission.progress >= mission.target:
            mission.completed_at = utcnow()
            granted = award_xp(
                db,
                user_id,
                amount=mission.xp_reward or rules.bonus_for("mission_completed"),
                kind=XPKind.MISSION,
                reason=f"Mission: {mission.title}",
                dedupe_key=bonus_key("mission", f"{day.isoformat()}:{mission.code}"),
                activity_date=day,
            )
            if granted:
                awarded[f"mission:{mission.code}"] = granted

    db.flush()
    return awarded


def _matches(
    db: Session, user_id: uuid.UUID, problem: Problem, params: dict[str, Any]
) -> bool:
    kind = params.get("kind", "any")

    if kind == "any":
        return True

    if kind == "min_rating":
        return bool(problem.rating and problem.rating >= params.get("min_rating", 0))

    if kind == "topic":
        slug = params.get("topic")
        topic = db.scalar(select(Topic).where(Topic.slug == slug))
        if topic is None:
            return False
        descendant_ids = db.scalars(
            select(Topic.id).where(
                (Topic.path == topic.path) | (Topic.path.like(f"{topic.path}/%"))
            )
        ).all()
        return bool(
            db.scalar(
                select(func.count(ProblemTopic.problem_id)).where(
                    ProblemTopic.problem_id == problem.id,
                    ProblemTopic.topic_id.in_(descendant_ids),
                )
            )
        )

    if kind == "cp31_bucket":
        return bool(
            db.scalar(
                select(func.count(SheetProblem.id))
                .join(SheetSection, SheetSection.id == SheetProblem.section_id)
                .join(Sheet, Sheet.id == SheetProblem.sheet_id)
                .where(
                    Sheet.slug == "cp31",
                    SheetProblem.problem_id == problem.id,
                    SheetSection.rating_bucket == params.get("bucket"),
                )
            )
        )

    # `review` missions advance through the review flow, not through solves.
    return False


def _sync_progress(
    db: Session, user_id: uuid.UUID, day: date, missions: list[DailyMission]
) -> None:
    """Recompute progress for count-based missions from activity."""
    activity = db.scalar(
        select(ActivityDay).where(
            ActivityDay.user_id == user_id, ActivityDay.activity_date == day
        )
    )
    if activity is None:
        return

    changed = False
    for mission in missions:
        params = mission.params or {}
        if params.get("kind") == "any" and mission.progress != activity.problems_solved:
            mission.progress = min(activity.problems_solved, mission.target)
            changed = True
        elif params.get("kind") == "review" and mission.progress != activity.reviews_completed:
            mission.progress = min(activity.reviews_completed, mission.target)
            changed = True

        if mission.progress >= mission.target and mission.completed_at is None:
            mission.completed_at = utcnow()
            award_xp(
                db,
                user_id,
                amount=mission.xp_reward,
                kind=XPKind.MISSION,
                reason=f"Mission: {mission.title}",
                dedupe_key=bonus_key("mission", f"{day.isoformat()}:{mission.code}"),
                activity_date=day,
            )
            changed = True

    if changed:
        db.commit()


def missions_for_today(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> list[dict[str, Any]]:
    missions = ensure_missions_for_today(db, user_id, tz)
    return [
        {
            "id": str(m.id),
            "code": m.code,
            "title": m.title,
            "description": m.description,
            "target": m.target,
            "progress": min(m.progress, m.target),
            "completed": m.completed_at is not None,
            "xp_reward": m.xp_reward,
        }
        for m in missions
    ]


def record_solve_day(db: Session, user_id: uuid.UUID, when) -> date:
    return local_date(when, user_timezone(db, user_id))
