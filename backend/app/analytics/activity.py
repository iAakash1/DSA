"""Activity heatmap and calendar."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import SOLVED_STATUSES
from app.models.gamification import ActivityDay
from app.models.problem import Problem
from app.models.progress import Submission, UserProblem
from app.utils.timeutils import day_bounds_utc, iter_dates, today_in

#: GitHub-style intensity buckets: 0, 1, 2-3, 4-5, 6+.
INTENSITY_THRESHOLDS = [(6, 4), (4, 3), (2, 2), (1, 1)]


def intensity_for(count: int) -> int:
    for threshold, level in INTENSITY_THRESHOLDS:
        if count >= threshold:
            return level
    return 0


def heatmap(
    db: Session, user_id: uuid.UUID, tz: str | None = None, days: int = 365
) -> dict[str, Any]:
    """365-day activity grid. Empty days are included so the grid is dense."""
    end = today_in(tz)
    start = end - timedelta(days=days - 1)

    rows = {
        row.activity_date: row
        for row in db.scalars(
            select(ActivityDay).where(
                ActivityDay.user_id == user_id,
                ActivityDay.activity_date >= start,
                ActivityDay.activity_date <= end,
            )
        ).all()
    }

    cells = []
    total_problems = 0
    total_xp = 0
    active_days = 0
    for day in iter_dates(start, end):
        row = rows.get(day)
        count = row.problems_solved if row else 0
        total_problems += count
        total_xp += row.xp_earned if row else 0
        if count > 0:
            active_days += 1
        cells.append(
            {
                "date": day.isoformat(),
                "count": count,
                "intensity": intensity_for(count),
                "xp": row.xp_earned if row else 0,
                "minutes": row.minutes_spent if row else 0,
                "contests": row.contests if row else 0,
                "upsolves": row.upsolves if row else 0,
                "reviews": row.reviews_completed if row else 0,
                "frozen": bool(row.is_frozen) if row else False,
            }
        )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": cells,
        "totals": {
            "problems": total_problems,
            "xp": total_xp,
            "active_days": active_days,
            "coverage": round(active_days / max(1, days), 3),
        },
    }


def day_detail(
    db: Session, user_id: uuid.UUID, day: date, tz: str | None = None
) -> dict[str, Any]:
    """Everything that happened on one local calendar day."""
    start_utc, end_utc = day_bounds_utc(day, tz)

    solved_rows = db.execute(
        select(Problem, UserProblem)
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status.in_(SOLVED_STATUSES),
            UserProblem.first_solved_at >= start_utc,
            UserProblem.first_solved_at < end_utc,
        )
        .order_by(UserProblem.first_solved_at)
    ).all()

    submissions = _count_submissions(db, user_id, start_utc, end_utc)

    activity = db.scalar(
        select(ActivityDay).where(
            ActivityDay.user_id == user_id, ActivityDay.activity_date == day
        )
    )

    return {
        "date": day.isoformat(),
        "problems": [
            {
                "id": str(problem.id),
                "title": problem.title,
                "platform": problem.platform,
                "external_id": problem.external_id,
                "rating": problem.rating,
                "difficulty": problem.difficulty,
                "url": problem.url,
                "solution_source": user_problem.best_solution_source,
                "solved_at": user_problem.first_solved_at.isoformat()
                if user_problem.first_solved_at
                else None,
            }
            for problem, user_problem in solved_rows
        ],
        "submissions": submissions,
        "xp": activity.xp_earned if activity else 0,
        "minutes": activity.minutes_spent if activity else 0,
        "contests": activity.contests if activity else 0,
        "upsolves": activity.upsolves if activity else 0,
        "reviews": activity.reviews_completed if activity else 0,
        "frozen": bool(activity.is_frozen) if activity else False,
        "topics": activity.topics_touched if activity else [],
    }


def _count_submissions(db: Session, user_id: uuid.UUID, start_utc, end_utc) -> int:
    return int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.user_id == user_id,
                Submission.submitted_at >= start_utc,
                Submission.submitted_at < end_utc,
            )
        )
        or 0
    )


def recent_activity(
    db: Session, user_id: uuid.UUID, limit: int = 15
) -> list[dict[str, Any]]:
    """Most recently solved problems, newest first."""
    rows = db.execute(
        select(Problem, UserProblem)
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.last_solved_at.is_not(None),
        )
        .order_by(UserProblem.last_solved_at.desc())
        .limit(limit)
    ).all()

    return [
        {
            "problem_id": str(problem.id),
            "title": problem.title,
            "platform": problem.platform,
            "external_id": problem.external_id,
            "rating": problem.rating,
            "difficulty": problem.difficulty,
            "url": problem.url,
            "status": user_problem.status,
            "solution_source": user_problem.best_solution_source,
            "solved_at": user_problem.last_solved_at.isoformat()
            if user_problem.last_solved_at
            else None,
        }
        for problem, user_problem in rows
    ]


def weekly_totals(
    db: Session, user_id: uuid.UUID, tz: str | None = None, weeks: int = 12
) -> list[dict[str, Any]]:
    from app.utils.timeutils import week_start

    end = today_in(tz)
    start = week_start(end) - timedelta(weeks=weeks - 1)

    rows = db.scalars(
        select(ActivityDay).where(
            ActivityDay.user_id == user_id,
            ActivityDay.activity_date >= start,
        )
    ).all()

    buckets: dict[date, dict[str, int]] = {}
    for row in rows:
        key = week_start(row.activity_date)
        bucket = buckets.setdefault(key, {"problems": 0, "xp": 0, "minutes": 0, "days": 0})
        bucket["problems"] += row.problems_solved
        bucket["xp"] += row.xp_earned
        bucket["minutes"] += row.minutes_spent
        if row.problems_solved:
            bucket["days"] += 1

    return [
        {"week": key.isoformat(), **value}
        for key, value in sorted(buckets.items())
    ]
