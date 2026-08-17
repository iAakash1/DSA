"""Overall statistics and difficulty progression.

Everything here is deterministic and derived from stored rows. This module is
the "what happened" layer; the AI never computes any of it.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import (
    SOLVED_STATUSES,
    Window,
    count_solved,
    independence_breakdown,
    mean,
    median,
    safe_ratio,
    solve_times,
    solved_problem_rows,
)
from app.models.enums import (
    MISTAKE_LABELS,
    REPORTED_SOURCES,
    Platform,
    SolutionSource,
)
from app.models.problem import Problem
from app.models.progress import Mistake, Submission, UserProblem
from app.utils.timeutils import utcnow

#: Minimum solves in a rating band before we will call it "comfortable".
_COMFORT_MIN_SOLVES = 3
#: Success rate a band must sustain to count as comfortable.
_COMFORT_SUCCESS = 0.6


def overview(db: Session, user_id: uuid.UUID, tz: str | None = None) -> dict[str, Any]:
    w7 = Window.trailing(7)
    w30 = Window.trailing(30)

    solved_total = count_solved(db, user_id)
    solved_7 = count_solved(db, user_id, w7.start)
    solved_30 = count_solved(db, user_id, w30.start)
    solved_prev_7 = _count_between(db, user_id, w7.previous_start, w7.start)
    solved_prev_30 = _count_between(db, user_id, w30.previous_start, w30.start)

    attempted = int(
        db.scalar(
            select(func.count(UserProblem.id)).where(
                UserProblem.user_id == user_id, UserProblem.attempts > 0
            )
        )
        or 0
    )

    independence = independence_breakdown(db, user_id)
    independence_30 = independence_breakdown(db, user_id, w30.start)

    times_all = solve_times(db, user_id)
    times_30 = solve_times(db, user_id, w30.start)

    ratings_all = _solved_ratings(db, user_id)
    ratings_30 = _solved_ratings(db, user_id, w30.start)
    ratings_prev_30 = _solved_ratings(db, user_id, w30.previous_start, w30.start)

    platform_counts = dict(
        db.execute(
            select(Problem.platform, func.count(UserProblem.id))
            .join(UserProblem, UserProblem.problem_id == Problem.id)
            .where(
                UserProblem.user_id == user_id,
                UserProblem.status.in_(SOLVED_STATUSES),
            )
            .group_by(Problem.platform)
        ).all()
    )

    difficulty_counts = dict(
        db.execute(
            select(Problem.difficulty, func.count(UserProblem.id))
            .join(UserProblem, UserProblem.problem_id == Problem.id)
            .where(
                UserProblem.user_id == user_id,
                UserProblem.status.in_(SOLVED_STATUSES),
                Problem.platform == Platform.LEETCODE,
            )
            .group_by(Problem.difficulty)
        ).all()
    )

    # Independence rates are computed over solves the user actually reported.
    # Synced solves carry no self-report, and dividing by them would understate
    # independence rather than admit the information is missing.
    reported_total = sum(
        independence.get(source, 0) for source in REPORTED_SOURCES
    )
    reported_30 = sum(
        independence_30.get(source, 0) for source in REPORTED_SOURCES
    )
    solved_count_for_rate = max(1, reported_total)

    return {
        "volume": {
            "solved_total": solved_total,
            "attempted_total": attempted,
            "solved_last_7_days": solved_7,
            "solved_previous_7_days": solved_prev_7,
            "solved_last_30_days": solved_30,
            "solved_previous_30_days": solved_prev_30,
            "volume_change_30d": _pct_change(solved_prev_30, solved_30),
            "unsolved_attempted": max(0, attempted - solved_total),
        },
        "difficulty": {
            "average_cf_rating": _round_or_none(mean(ratings_all)),
            "median_cf_rating": _round_or_none(median(ratings_all)),
            "highest_cf_rating": int(max(ratings_all)) if ratings_all else None,
            "average_cf_rating_last_30_days": _round_or_none(mean(ratings_30)),
            "average_cf_rating_previous_30_days": _round_or_none(mean(ratings_prev_30)),
            "rating_change_30d": _delta(mean(ratings_prev_30), mean(ratings_30)),
            "comfortable_rating": comfortable_rating(db, user_id),
            "leetcode_difficulty_counts": {
                str(k): int(v) for k, v in difficulty_counts.items()
            },
        },
        "time": {
            "average_solve_minutes": _round_or_none(mean(times_all), 1),
            "median_solve_minutes": _round_or_none(median(times_all), 1),
            "average_solve_minutes_last_30_days": _round_or_none(mean(times_30), 1),
            "fastest_solve_minutes": _round_or_none(min(times_all), 1) if times_all else None,
            "slowest_solve_minutes": _round_or_none(max(times_all), 1) if times_all else None,
            "sessions_with_timing": len(times_all),
        },
        "independence": {
            "counts": independence,
            "reported_solves": reported_total,
            "unreported_solves": independence.get(SolutionSource.UNKNOWN, 0),
            #: Rates below are shares of `reported_solves`, not of all solves.
            "basis": "reported",
            "independent_rate": round(
                safe_ratio(independence.get(SolutionSource.INDEPENDENT, 0), solved_count_for_rate),
                3,
            ),
            "editorial_rate": round(
                safe_ratio(independence.get(SolutionSource.EDITORIAL, 0), solved_count_for_rate),
                3,
            ),
            "hint_rate": round(
                safe_ratio(independence.get(SolutionSource.HINT, 0), solved_count_for_rate), 3
            ),
            "independent_rate_last_30_days": round(
                safe_ratio(
                    independence_30.get(SolutionSource.INDEPENDENT, 0),
                    max(1, reported_30),
                ),
                3,
            ),
        },
        "platforms": {str(k): int(v) for k, v in platform_counts.items()},
        "mistakes": mistake_distribution(db, user_id),
        "success_rate": round(safe_ratio(solved_total, max(1, attempted)), 3),
    }


def _count_between(db: Session, user_id: uuid.UUID, start, end) -> int:
    return int(
        db.scalar(
            select(func.count(UserProblem.id)).where(
                UserProblem.user_id == user_id,
                UserProblem.status.in_(SOLVED_STATUSES),
                UserProblem.first_solved_at >= start,
                UserProblem.first_solved_at < end,
            )
        )
        or 0
    )


def _solved_ratings(
    db: Session, user_id: uuid.UUID, since=None, until=None
) -> list[float]:
    query = (
        select(Problem.rating)
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status.in_(SOLVED_STATUSES),
            UserProblem.first_solved_at.is_not(None),
            Problem.rating.is_not(None),
        )
    )
    if since is not None:
        query = query.where(UserProblem.first_solved_at >= since)
    if until is not None:
        query = query.where(UserProblem.first_solved_at < until)
    return [float(r) for r in db.scalars(query).all() if r]


def comfortable_rating(db: Session, user_id: uuid.UUID) -> int | None:
    """The highest rating band the user reliably handles.

    Deliberately NOT "highest problem ever solved" — one lucky 1900 does not
    make someone a 1900 solver. A band counts only with enough solves and a
    sustained success rate.
    """
    rows = db.execute(
        select(Problem.rating, UserProblem.status, UserProblem.attempts)
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(
            UserProblem.user_id == user_id,
            Problem.rating.is_not(None),
            UserProblem.attempts > 0,
        )
    ).all()
    if not rows:
        return None

    buckets: dict[int, dict[str, int]] = defaultdict(lambda: {"solved": 0, "attempted": 0})
    for rating, status, _attempts in rows:
        bucket = int(rating // 100 * 100)
        buckets[bucket]["attempted"] += 1
        if status in SOLVED_STATUSES:
            buckets[bucket]["solved"] += 1

    comfortable = None
    for bucket in sorted(buckets):
        data = buckets[bucket]
        if (
            data["solved"] >= _COMFORT_MIN_SOLVES
            and safe_ratio(data["solved"], data["attempted"]) >= _COMFORT_SUCCESS
        ):
            comfortable = bucket
    return comfortable


def difficulty_progression(
    db: Session, user_id: uuid.UUID, months: int = 12
) -> dict[str, Any]:
    """Monthly average/max solved rating — is difficulty actually rising?"""
    rows = solved_problem_rows(db, user_id, since=utcnow() - timedelta(days=months * 31))
    monthly: dict[str, list[float]] = defaultdict(list)
    monthly_counts: Counter[str] = Counter()

    for user_problem, problem in rows:
        if not user_problem.first_solved_at:
            continue
        key = user_problem.first_solved_at.strftime("%Y-%m")
        monthly_counts[key] += 1
        if problem.rating:
            monthly[key].append(float(problem.rating))

    series = [
        {
            "month": month,
            "solved": monthly_counts[month],
            "average_rating": _round_or_none(mean(values)),
            "max_rating": int(max(values)) if values else None,
        }
        for month, values in sorted(
            ((m, monthly.get(m, [])) for m in monthly_counts), key=lambda x: x[0]
        )
    ]

    ratings = _solved_ratings(db, user_id)
    buckets = Counter(int(r // 100 * 100) for r in ratings)

    return {
        "monthly": series,
        "rating_distribution": [
            {"rating": bucket, "solved": count} for bucket, count in sorted(buckets.items())
        ],
        "comfortable_rating": comfortable_rating(db, user_id),
        "highest_rating": int(max(ratings)) if ratings else None,
        "average_rating": _round_or_none(mean(ratings)),
    }


def mistake_distribution(
    db: Session, user_id: uuid.UUID, limit: int | None = None
) -> dict[str, Any]:
    rows = db.execute(
        select(Mistake.mistake_type, func.count(Mistake.id))
        .where(Mistake.user_id == user_id)
        .group_by(Mistake.mistake_type)
        .order_by(func.count(Mistake.id).desc())
    ).all()

    total = sum(int(c) for _, c in rows)
    items = [
        {
            "type": mistake_type,
            "label": MISTAKE_LABELS.get(mistake_type, mistake_type),
            "count": int(count),
            "share": round(safe_ratio(int(count), max(1, total)), 3),
        }
        for mistake_type, count in rows
    ]
    if limit:
        items = items[:limit]

    from app.models.enums import CONCEPTUAL_MISTAKES, IMPLEMENTATION_MISTAKES

    implementation = sum(i["count"] for i in items if i["type"] in IMPLEMENTATION_MISTAKES)
    conceptual = sum(i["count"] for i in items if i["type"] in CONCEPTUAL_MISTAKES)

    return {
        "total": total,
        "items": items,
        "implementation_count": implementation,
        "conceptual_count": conceptual,
        #: >0.5 means bugs, not misunderstanding, are the bottleneck.
        "implementation_share": round(
            safe_ratio(implementation, max(1, implementation + conceptual)), 3
        ),
    }


def solve_time_by_topic(db: Session, user_id: uuid.UUID, tz: str | None = None) -> list[dict]:
    from app.analytics.mastery import topic_mastery

    return [
        {
            "topic": stats.name,
            "slug": stats.slug,
            "average_minutes": round(stats.avg_time_minutes, 1),
            "solved": stats.solved,
        }
        for stats in topic_mastery(db, user_id, tz)
        if stats.avg_time_minutes is not None and stats.solved >= 2
    ]


def submission_stats(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    total = int(
        db.scalar(select(func.count(Submission.id)).where(Submission.user_id == user_id))
        or 0
    )
    accepted = int(
        db.scalar(
            select(func.count(Submission.id)).where(
                Submission.user_id == user_id, Submission.is_accepted.is_(True)
            )
        )
        or 0
    )
    verdicts = dict(
        db.execute(
            select(Submission.verdict, func.count(Submission.id))
            .where(Submission.user_id == user_id, Submission.is_accepted.is_(False))
            .group_by(Submission.verdict)
            .order_by(func.count(Submission.id).desc())
            .limit(8)
        ).all()
    )
    return {
        "total": total,
        "accepted": accepted,
        "acceptance_rate": round(safe_ratio(accepted, max(1, total)), 3),
        "top_failure_verdicts": {str(k): int(v) for k, v in verdicts.items()},
    }


def _pct_change(previous: float | int | None, current: float | int | None) -> float | None:
    if not previous:
        return None
    if current is None:
        return None
    return round((current - previous) / previous * 100, 1)


def _delta(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None:
        return None
    return round(current - previous, 1)


def _round_or_none(value: float | None, digits: int = 0) -> float | int | None:
    if value is None:
        return None
    return round(value, digits) if digits else round(value)
