"""Data-driven achievements.

Definitions live in data, not code: adding an achievement means adding a row to
`ACHIEVEMENT_DEFINITIONS`. Evaluation builds one metrics snapshot and tests
every locked achievement against it, so unlocking is a single pass rather than
N queries.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.contest import ContestParticipation
from app.models.enums import (
    Difficulty,
    Platform,
    ProblemStatus,
    SolutionSource,
    XPKind,
)
from app.models.gamification import Achievement, ActivityDay, UserAchievement
from app.models.problem import Problem, ProblemTopic, Topic
from app.models.progress import Review, UserProblem
from app.models.sheet import Sheet, SheetProblem, SheetSection
from app.utils.timeutils import today_in, utcnow

log = get_logger(__name__)

ACHIEVEMENT_DEFINITIONS: list[dict[str, Any]] = [
    # --- volume -----------------------------------------------------------
    {"code": "first_blood", "name": "First Blood", "description": "Solve your first problem.", "category": "volume", "tier": "bronze", "icon": "swords", "xp_reward": 25, "criteria": {"type": "problems_solved", "count": 1}},
    {"code": "solved_10", "name": "Getting Started", "description": "Solve 10 problems.", "category": "volume", "tier": "bronze", "icon": "target", "xp_reward": 50, "criteria": {"type": "problems_solved", "count": 10}},
    {"code": "solved_50", "name": "Building Momentum", "description": "Solve 50 problems.", "category": "volume", "tier": "silver", "icon": "trending-up", "xp_reward": 150, "criteria": {"type": "problems_solved", "count": 50}},
    {"code": "solved_100", "name": "Century", "description": "Solve 100 problems.", "category": "volume", "tier": "silver", "icon": "award", "xp_reward": 300, "criteria": {"type": "problems_solved", "count": 100}},
    {"code": "solved_500", "name": "Grinder", "description": "Solve 500 problems.", "category": "volume", "tier": "gold", "icon": "flame", "xp_reward": 1000, "criteria": {"type": "problems_solved", "count": 500}},
    {"code": "solved_1000", "name": "Four Digits", "description": "Solve 1000 problems.", "category": "volume", "tier": "platinum", "icon": "crown", "xp_reward": 2500, "criteria": {"type": "problems_solved", "count": 1000}},
    # --- consistency ------------------------------------------------------
    {"code": "streak_7", "name": "Week Streak", "description": "Solve on 7 consecutive days.", "category": "consistency", "tier": "bronze", "icon": "flame", "xp_reward": 75, "criteria": {"type": "streak", "days": 7}},
    {"code": "streak_30", "name": "Month Streak", "description": "Solve on 30 consecutive days.", "category": "consistency", "tier": "silver", "icon": "flame", "xp_reward": 300, "criteria": {"type": "streak", "days": 30}},
    {"code": "streak_100", "name": "Unbreakable", "description": "Solve on 100 consecutive days.", "category": "consistency", "tier": "gold", "icon": "flame", "xp_reward": 1200, "criteria": {"type": "streak", "days": 100}},
    {"code": "month_100", "name": "Heavy Month", "description": "Solve 100 problems in a 30-day window.", "category": "consistency", "tier": "gold", "icon": "calendar", "xp_reward": 500, "criteria": {"type": "problems_in_window", "count": 100, "days": 30}},
    # --- difficulty -------------------------------------------------------
    {"code": "first_hard", "name": "Into the Deep", "description": "Solve your first LeetCode Hard.", "category": "difficulty", "tier": "silver", "icon": "mountain", "xp_reward": 100, "criteria": {"type": "difficulty_solved", "difficulty": "hard", "count": 1}},
    {"code": "cf_1400", "name": "Pupil Territory", "description": "Solve a 1400+ rated Codeforces problem.", "category": "difficulty", "tier": "silver", "icon": "chevrons-up", "xp_reward": 100, "criteria": {"type": "rating_solved", "min_rating": 1400}},
    {"code": "cf_1600", "name": "Specialist Territory", "description": "Solve a 1600+ rated Codeforces problem.", "category": "difficulty", "tier": "gold", "icon": "chevrons-up", "xp_reward": 200, "criteria": {"type": "rating_solved", "min_rating": 1600}},
    {"code": "cf_1800", "name": "Expert Territory", "description": "Solve an 1800+ rated Codeforces problem.", "category": "difficulty", "tier": "gold", "icon": "chevrons-up", "xp_reward": 400, "criteria": {"type": "rating_solved", "min_rating": 1800}},
    {"code": "cf_2000", "name": "Candidate Master Territory", "description": "Solve a 2000+ rated Codeforces problem.", "category": "difficulty", "tier": "platinum", "icon": "rocket", "xp_reward": 800, "criteria": {"type": "rating_solved", "min_rating": 2000}},
    # --- quality ----------------------------------------------------------
    {"code": "independent_50", "name": "On Your Own", "description": "Solve 50 problems independently.", "category": "quality", "tier": "silver", "icon": "brain", "xp_reward": 250, "criteria": {"type": "independent_solves", "count": 50}},
    {"code": "independent_200", "name": "Self-Reliant", "description": "Solve 200 problems independently.", "category": "quality", "tier": "gold", "icon": "brain", "xp_reward": 750, "criteria": {"type": "independent_solves", "count": 200}},
    {"code": "reviews_25", "name": "Retention", "description": "Complete 25 spaced reviews.", "category": "quality", "tier": "silver", "icon": "repeat", "xp_reward": 200, "criteria": {"type": "reviews_completed", "count": 25}},
    # --- topics -----------------------------------------------------------
    {"code": "graph_master", "name": "Graph Master", "description": "Solve 40 graph problems.", "category": "topic", "tier": "gold", "icon": "git-branch", "xp_reward": 300, "criteria": {"type": "topic_solved", "topic": "graphs", "count": 40}},
    {"code": "dp_grinder", "name": "DP Grinder", "description": "Solve 40 dynamic programming problems.", "category": "topic", "tier": "gold", "icon": "layers", "xp_reward": 300, "criteria": {"type": "topic_solved", "topic": "dynamic-programming", "count": 40}},
    {"code": "binary_search_specialist", "name": "Binary Search Specialist", "description": "Solve 25 binary search problems.", "category": "topic", "tier": "silver", "icon": "search", "xp_reward": 200, "criteria": {"type": "topic_solved", "topic": "binary-search", "count": 25}},
    {"code": "tree_climber", "name": "Tree Climber", "description": "Solve 30 tree problems.", "category": "topic", "tier": "silver", "icon": "tree-pine", "xp_reward": 200, "criteria": {"type": "topic_solved", "topic": "trees", "count": 30}},
    # --- sheets -----------------------------------------------------------
    {"code": "cp31_800", "name": "CP-31: 800 Cleared", "description": "Complete the CP-31 800 bucket.", "category": "sheet", "tier": "bronze", "icon": "check-circle", "xp_reward": 200, "criteria": {"type": "sheet_section_complete", "sheet": "cp31", "bucket": 800}},
    {"code": "cp31_1000", "name": "CP-31: 1000 Cleared", "description": "Complete the CP-31 1000 bucket.", "category": "sheet", "tier": "silver", "icon": "check-circle", "xp_reward": 300, "criteria": {"type": "sheet_section_complete", "sheet": "cp31", "bucket": 1000}},
    {"code": "cp31_1200", "name": "CP-31: 1200 Cleared", "description": "Complete the CP-31 1200 bucket.", "category": "sheet", "tier": "gold", "icon": "check-circle", "xp_reward": 400, "criteria": {"type": "sheet_section_complete", "sheet": "cp31", "bucket": 1200}},
    {"code": "cp31_1400", "name": "CP-31: 1400 Cleared", "description": "Complete the CP-31 1400 bucket.", "category": "sheet", "tier": "platinum", "icon": "check-circle", "xp_reward": 600, "criteria": {"type": "sheet_section_complete", "sheet": "cp31", "bucket": 1400}},
    {"code": "striver_half", "name": "A2Z Halfway", "description": "Complete half of Striver's A2Z sheet.", "category": "sheet", "tier": "gold", "icon": "book-open", "xp_reward": 500, "criteria": {"type": "sheet_percent", "sheet": "striver-a2z", "percent": 50}},
    # --- contests ---------------------------------------------------------
    {"code": "first_contest", "name": "Contest Debut", "description": "Record your first contest.", "category": "contest", "tier": "bronze", "icon": "trophy", "xp_reward": 50, "criteria": {"type": "contests", "count": 1}},
    {"code": "contests_10", "name": "Regular Competitor", "description": "Record 10 contests.", "category": "contest", "tier": "silver", "icon": "trophy", "xp_reward": 250, "criteria": {"type": "contests", "count": 10}},
    {"code": "upsolve_25", "name": "Upsolver", "description": "Upsolve 25 contest problems.", "category": "contest", "tier": "gold", "icon": "arrow-up-circle", "xp_reward": 400, "criteria": {"type": "upsolves", "count": 25}},
    # --- xp ---------------------------------------------------------------
    {"code": "xp_1000", "name": "1,000 XP", "description": "Earn 1,000 XP.", "category": "xp", "tier": "bronze", "icon": "zap", "xp_reward": 0, "criteria": {"type": "xp", "amount": 1000}},
    {"code": "xp_10000", "name": "10,000 XP", "description": "Earn 10,000 XP.", "category": "xp", "tier": "gold", "icon": "zap", "xp_reward": 0, "criteria": {"type": "xp", "amount": 10000}},
]


def seed_achievements(db: Session) -> int:
    """Idempotently insert/refresh achievement definitions."""
    created = 0
    for order, spec in enumerate(ACHIEVEMENT_DEFINITIONS):
        existing = db.scalar(
            select(Achievement).where(Achievement.code == spec["code"])
        )
        if existing is None:
            db.add(
                Achievement(
                    code=spec["code"],
                    name=spec["name"],
                    description=spec["description"],
                    category=spec["category"],
                    tier=spec["tier"],
                    icon=spec.get("icon"),
                    criteria=spec["criteria"],
                    xp_reward=spec.get("xp_reward", 0),
                    sort_order=order,
                )
            )
            created += 1
        else:
            existing.name = spec["name"]
            existing.description = spec["description"]
            existing.criteria = spec["criteria"]
            existing.xp_reward = spec.get("xp_reward", 0)
            existing.tier = spec["tier"]
            existing.icon = spec.get("icon")
            existing.sort_order = order
    db.commit()
    log.info("achievements seeded", created=created, total=len(ACHIEVEMENT_DEFINITIONS))
    return created


_SOLVED_STATUSES = (
    ProblemStatus.SOLVED,
    ProblemStatus.MASTERED,
    ProblemStatus.REVISIT,
)


def build_metrics(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """One snapshot of everything the criteria vocabulary can test."""
    from app.gamification.streaks import compute_streak
    from app.gamification.xp import total_xp

    solved_filter = (
        UserProblem.user_id == user_id,
        UserProblem.status.in_(_SOLVED_STATUSES),
    )

    problems_solved = int(
        db.scalar(select(func.count(UserProblem.id)).where(*solved_filter)) or 0
    )
    independent = int(
        db.scalar(
            select(func.count(UserProblem.id)).where(
                *solved_filter,
                UserProblem.best_solution_source == SolutionSource.INDEPENDENT,
            )
        )
        or 0
    )
    max_rating = db.scalar(
        select(func.max(Problem.rating))
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(*solved_filter, Problem.platform == Platform.CODEFORCES)
    )
    hard_solved = int(
        db.scalar(
            select(func.count(UserProblem.id))
            .join(Problem, UserProblem.problem_id == Problem.id)
            .where(*solved_filter, Problem.difficulty == Difficulty.HARD)
        )
        or 0
    )
    contests = int(
        db.scalar(
            select(func.count(ContestParticipation.id)).where(
                ContestParticipation.user_id == user_id
            )
        )
        or 0
    )
    upsolves = int(
        db.scalar(
            select(func.coalesce(func.sum(ContestParticipation.problems_upsolved), 0)).where(
                ContestParticipation.user_id == user_id
            )
        )
        or 0
    )
    reviews_done = int(
        db.scalar(
            select(func.count(Review.id)).where(
                Review.user_id == user_id, Review.completed_at.is_not(None)
            )
        )
        or 0
    )

    streak = compute_streak(db, user_id)

    # Topic counts roll up through the materialized path so solving a Dijkstra
    # problem also counts toward "Graphs".
    topic_counts: dict[str, int] = {}
    topic_rows = db.execute(
        select(Topic.path, func.count(func.distinct(UserProblem.problem_id)))
        .select_from(UserProblem)
        .join(ProblemTopic, ProblemTopic.problem_id == UserProblem.problem_id)
        .join(Topic, Topic.id == ProblemTopic.topic_id)
        .where(*solved_filter)
        .group_by(Topic.path)
    ).all()
    for path, count in topic_rows:
        for ancestor in (path or "").split("/"):
            if ancestor:
                topic_counts[ancestor] = topic_counts.get(ancestor, 0) + int(count)

    return {
        "problems_solved": problems_solved,
        "independent_solves": independent,
        "max_cf_rating_solved": int(max_rating) if max_rating else 0,
        "hard_solved": hard_solved,
        "contests": contests,
        "upsolves": upsolves,
        "reviews_completed": reviews_done,
        "current_streak": streak.current,
        "longest_streak": streak.longest,
        "total_xp": total_xp(db, user_id),
        "topic_counts": topic_counts,
    }


def _problems_in_window(db: Session, user_id: uuid.UUID, days: int) -> int:
    tz_today = today_in(None)
    start = tz_today - timedelta(days=days)
    return int(
        db.scalar(
            select(func.coalesce(func.sum(ActivityDay.problems_solved), 0)).where(
                ActivityDay.user_id == user_id, ActivityDay.activity_date >= start
            )
        )
        or 0
    )


def _sheet_section_complete(
    db: Session, user_id: uuid.UUID, sheet_slug: str, bucket: int
) -> bool:
    section = db.scalar(
        select(SheetSection)
        .join(Sheet, Sheet.id == SheetSection.sheet_id)
        .where(Sheet.slug == sheet_slug, SheetSection.rating_bucket == bucket)
    )
    if section is None:
        return False
    total = int(
        db.scalar(
            select(func.count(SheetProblem.id)).where(
                SheetProblem.section_id == section.id
            )
        )
        or 0
    )
    if total == 0:
        return False
    solved = int(
        db.scalar(
            select(func.count(SheetProblem.id))
            .join(UserProblem, UserProblem.problem_id == SheetProblem.problem_id)
            .where(
                SheetProblem.section_id == section.id,
                UserProblem.user_id == user_id,
                UserProblem.status.in_(_SOLVED_STATUSES),
            )
        )
        or 0
    )
    return solved >= total


def _sheet_percent(db: Session, user_id: uuid.UUID, sheet_slug: str) -> float:
    sheet = db.scalar(select(Sheet).where(Sheet.slug == sheet_slug))
    if sheet is None:
        return 0.0
    total = int(
        db.scalar(
            select(func.count(SheetProblem.id)).where(SheetProblem.sheet_id == sheet.id)
        )
        or 0
    )
    if total == 0:
        return 0.0
    solved = int(
        db.scalar(
            select(func.count(SheetProblem.id))
            .join(UserProblem, UserProblem.problem_id == SheetProblem.problem_id)
            .where(
                SheetProblem.sheet_id == sheet.id,
                UserProblem.user_id == user_id,
                UserProblem.status.in_(_SOLVED_STATUSES),
            )
        )
        or 0
    )
    return solved / total * 100


def _satisfied(
    db: Session, user_id: uuid.UUID, criteria: dict[str, Any], metrics: dict[str, Any]
) -> bool:
    kind = criteria.get("type")
    if kind == "problems_solved":
        return metrics["problems_solved"] >= criteria["count"]
    if kind == "independent_solves":
        return metrics["independent_solves"] >= criteria["count"]
    if kind == "streak":
        return metrics["longest_streak"] >= criteria["days"]
    if kind == "xp":
        return metrics["total_xp"] >= criteria["amount"]
    if kind == "rating_solved":
        return metrics["max_cf_rating_solved"] >= criteria["min_rating"]
    if kind == "difficulty_solved":
        return metrics["hard_solved"] >= criteria.get("count", 1)
    if kind == "contests":
        return metrics["contests"] >= criteria["count"]
    if kind == "upsolves":
        return metrics["upsolves"] >= criteria["count"]
    if kind == "reviews_completed":
        return metrics["reviews_completed"] >= criteria["count"]
    if kind == "topic_solved":
        return metrics["topic_counts"].get(criteria["topic"], 0) >= criteria["count"]
    if kind == "problems_in_window":
        return _problems_in_window(db, user_id, criteria["days"]) >= criteria["count"]
    if kind == "sheet_section_complete":
        return _sheet_section_complete(db, user_id, criteria["sheet"], criteria["bucket"])
    if kind == "sheet_percent":
        return _sheet_percent(db, user_id, criteria["sheet"]) >= criteria["percent"]
    log.warning("unknown achievement criteria", type=kind)
    return False


def evaluate_achievements(db: Session, user_id: uuid.UUID) -> list[Achievement]:
    """Unlock everything newly earned. Returns the newly unlocked rows."""
    from app.gamification.xp import award_xp

    unlocked_ids = set(
        db.scalars(
            select(UserAchievement.achievement_id).where(
                UserAchievement.user_id == user_id
            )
        ).all()
    )
    candidates = [
        a
        for a in db.scalars(select(Achievement).order_by(Achievement.sort_order)).all()
        if a.id not in unlocked_ids
    ]
    if not candidates:
        return []

    metrics = build_metrics(db, user_id)
    today = today_in(None)
    newly: list[Achievement] = []

    for achievement in candidates:
        try:
            if not _satisfied(db, user_id, achievement.criteria or {}, metrics):
                continue
        except (KeyError, TypeError) as exc:
            log.warning(
                "malformed achievement criteria",
                code=achievement.code,
                error=str(exc),
            )
            continue

        db.add(
            UserAchievement(
                user_id=user_id,
                achievement_id=achievement.id,
                unlocked_at=utcnow(),
                progress=1.0,
            )
        )
        if achievement.xp_reward:
            award_xp(
                db,
                user_id,
                amount=achievement.xp_reward,
                kind=XPKind.ACHIEVEMENT,
                reason=f"Achievement: {achievement.name}",
                dedupe_key=f"achievement:{achievement.code}",
                activity_date=today,
            )
        newly.append(achievement)

    if newly:
        db.commit()
        log.info(
            "achievements unlocked",
            user_id=str(user_id),
            codes=[a.code for a in newly],
        )
    return newly
