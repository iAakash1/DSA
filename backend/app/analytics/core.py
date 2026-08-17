"""Shared analytics primitives."""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ProblemStatus, SolutionSource
from app.models.problem import Problem
from app.models.progress import SolvingSession, UserProblem
from app.utils.timeutils import today_in, utcnow

SOLVED_STATUSES = (
    ProblemStatus.SOLVED,
    ProblemStatus.MASTERED,
    ProblemStatus.REVISIT,
)

#: LeetCode difficulty mapped onto the 0-1 axis used for difficulty scoring.
DIFFICULTY_SCALE = {"easy": 0.30, "medium": 0.62, "hard": 1.0, "unknown": 0.45}

#: Rating range used to normalize Codeforces difficulty into 0-1.
RATING_FLOOR = 800
RATING_CEILING = 2000

MASTERY_BANDS = [
    (81, "Mastered"),
    (61, "Strong"),
    (41, "Developing"),
    (21, "Familiar"),
    (0, "Beginner"),
]


def mastery_band(score: float) -> str:
    for threshold, label in MASTERY_BANDS:
        if score >= threshold:
            return label
    return "Beginner"


def normalize_rating(rating: int | None) -> float:
    if rating is None:
        return 0.45
    span = RATING_CEILING - RATING_FLOOR
    return max(0.0, min(1.0, (rating - RATING_FLOOR) / span))


def difficulty_value(difficulty: str | None, rating: int | None) -> float:
    if rating is not None:
        return normalize_rating(rating)
    return DIFFICULTY_SCALE.get((difficulty or "unknown").lower(), 0.45)


def recency_factor(days_since: int | None, half_life: int = 30) -> float:
    """1.0 when practiced today, decaying toward 0 as it goes stale."""
    if days_since is None:
        return 0.0
    return float(0.5 ** (max(0, days_since) / half_life))


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def median(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return float(statistics.median(clean)) if clean else None


def mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return float(statistics.fmean(clean)) if clean else None


@dataclass(frozen=True)
class Window:
    """A comparison window: the last `days` days, and the `days` before that."""

    days: int
    start: datetime
    previous_start: datetime
    end: datetime

    @classmethod
    def trailing(cls, days: int) -> "Window":
        end = utcnow()
        start = end - timedelta(days=days)
        return cls(days=days, start=start, previous_start=start - timedelta(days=days), end=end)


def solved_problem_rows(
    db: Session,
    user_id: uuid.UUID,
    *,
    since: datetime | None = None,
) -> list[tuple[UserProblem, Problem]]:
    query = (
        select(UserProblem, Problem)
        .join(Problem, Problem.id == UserProblem.problem_id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status.in_(SOLVED_STATUSES),
            UserProblem.first_solved_at.is_not(None),
        )
    )
    if since is not None:
        query = query.where(UserProblem.first_solved_at >= since)
    return [(up, p) for up, p in db.execute(query).all()]


def count_solved(
    db: Session, user_id: uuid.UUID, since: datetime | None = None
) -> int:
    query = select(func.count(UserProblem.id)).where(
        UserProblem.user_id == user_id,
        UserProblem.status.in_(SOLVED_STATUSES),
        UserProblem.first_solved_at.is_not(None),
    )
    if since is not None:
        query = query.where(UserProblem.first_solved_at >= since)
    return int(db.scalar(query) or 0)


def independence_breakdown(
    db: Session, user_id: uuid.UUID, since: datetime | None = None
) -> dict[str, int]:
    query = (
        select(UserProblem.best_solution_source, func.count(UserProblem.id))
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status.in_(SOLVED_STATUSES),
            UserProblem.first_solved_at.is_not(None),
        )
        .group_by(UserProblem.best_solution_source)
    )
    if since is not None:
        query = query.where(UserProblem.first_solved_at >= since)

    counts = {source.value: 0 for source in SolutionSource}
    for source, count in db.execute(query).all():
        if source:
            counts[source] = int(count)
    return counts


def solve_times(
    db: Session, user_id: uuid.UUID, since: datetime | None = None
) -> list[float]:
    query = select(SolvingSession.time_spent_seconds).where(
        SolvingSession.user_id == user_id,
        SolvingSession.result == "solved",
        SolvingSession.time_spent_seconds.is_not(None),
        SolvingSession.time_spent_seconds > 0,
    )
    if since is not None:
        query = query.where(SolvingSession.finished_at >= since)
    return [float(v) / 60.0 for v in db.scalars(query).all() if v]


def days_since_local(dt: datetime | None, tz: str | None) -> int | None:
    if dt is None:
        return None
    from app.utils.timeutils import local_date

    return (today_in(tz) - local_date(dt, tz)).days


def period_label(days: int) -> str:
    if days == 7:
        return "last 7 days"
    if days == 30:
        return "last 30 days"
    if days == 90:
        return "last 90 days"
    return f"last {days} days"


def date_range(days: int, tz: str | None) -> tuple[date, date]:
    end = today_in(tz)
    return end - timedelta(days=days - 1), end
