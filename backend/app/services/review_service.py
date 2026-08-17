"""Spaced repetition for algorithms.

A problem enters the review queue because of a *signal*, not because time
passed. Solving something only after reading the editorial is the clearest
signal there is that you have not actually learned it yet.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.enums import (
    ProblemStatus,
    ReviewReason,
    SolutionSource,
    XPKind,
)
from app.models.problem import Pattern, Problem, ProblemPattern
from app.models.progress import Review, UserProblem
from app.utils.timeutils import utcnow

log = get_logger(__name__)

#: Standard expanding intervals, in days.
REVIEW_INTERVALS = [1, 3, 7, 14, 30]

#: Signal -> (initial interval in days, human explanation).
_TRIGGERS: dict[str, tuple[int, str]] = {
    ReviewReason.LOW_CONFIDENCE: (1, "You rated your confidence 2/5 or lower."),
    ReviewReason.USED_EDITORIAL: (3, "You solved this after reading the editorial."),
    ReviewReason.REPEATED_MISTAKE: (3, "You recorded a mistake on this problem."),
    ReviewReason.MULTIPLE_FAILURES: (3, "This took several attempts before it worked."),
    ReviewReason.IMPORTANT_PATTERN: (7, "This is a core pattern worth reinforcing."),
    ReviewReason.STALE: (30, "You have not revisited this in a long time."),
    ReviewReason.MANUAL: (3, "You queued this for review yourself."),
}


def next_interval(current: int) -> int:
    for interval in REVIEW_INTERVALS:
        if interval > current:
            return interval
    return REVIEW_INTERVALS[-1]


def schedule_review_after_solve(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    *,
    solution_source: str,
    confidence: int | None,
    attempts: int,
    mistakes: list[str],
) -> Review | None:
    """Queue a review when the solve carried a weakness signal.

    The most urgent applicable trigger wins; only one open review exists per
    problem at a time.
    """
    reasons: list[str] = []
    if confidence is not None and confidence <= 2:
        reasons.append(ReviewReason.LOW_CONFIDENCE)
    if solution_source in (
        SolutionSource.EDITORIAL,
        SolutionSource.DISCUSSION,
        SolutionSource.COPIED,
    ):
        reasons.append(ReviewReason.USED_EDITORIAL)
    if mistakes:
        reasons.append(ReviewReason.REPEATED_MISTAKE)
    if attempts >= 3:
        reasons.append(ReviewReason.MULTIPLE_FAILURES)
    if _is_core_pattern(db, problem_id):
        reasons.append(ReviewReason.IMPORTANT_PATTERN)

    if not reasons:
        return None

    reason = min(reasons, key=lambda r: _TRIGGERS[r][0])
    interval, detail = _TRIGGERS[reason]
    return _upsert_review(db, user_id, problem_id, reason, detail, interval)


def queue_review(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    reason: str = ReviewReason.MANUAL,
    interval_days: int | None = None,
) -> Review:
    detail = _TRIGGERS.get(reason, (3, "Queued for review."))[1]
    interval = interval_days or _TRIGGERS.get(reason, (3, ""))[0]
    review = _upsert_review(db, user_id, problem_id, reason, detail, interval)
    db.commit()
    return review


def _upsert_review(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    reason: str,
    detail: str,
    interval_days: int,
) -> Review:
    open_review = db.scalar(
        select(Review).where(
            Review.user_id == user_id,
            Review.problem_id == problem_id,
            Review.completed_at.is_(None),
        )
    )
    scheduled_for = utcnow() + timedelta(days=interval_days)

    if open_review is not None:
        # Keep the more urgent of the two schedules.
        if scheduled_for < open_review.scheduled_for:
            open_review.scheduled_for = scheduled_for
            open_review.reason = reason
            open_review.reason_detail = detail
            open_review.interval_days = interval_days
        review = open_review
    else:
        review = Review(
            user_id=user_id,
            problem_id=problem_id,
            reason=reason,
            reason_detail=detail,
            scheduled_for=scheduled_for,
            interval_days=interval_days,
        )
        db.add(review)

    user_problem = db.scalar(
        select(UserProblem).where(
            UserProblem.user_id == user_id, UserProblem.problem_id == problem_id
        )
    )
    if user_problem is not None:
        user_problem.needs_review = True
        user_problem.review_due_at = review.scheduled_for
        user_problem.review_interval_days = interval_days

    db.flush()
    return review


def _is_core_pattern(db: Session, problem_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(func.count(Pattern.id))
            .join(ProblemPattern, ProblemPattern.pattern_id == Pattern.id)
            .where(ProblemPattern.problem_id == problem_id, Pattern.is_core.is_(True))
        )
    )


def get_due_reviews(
    db: Session, user_id: uuid.UUID, limit: int = 25, include_upcoming: bool = False
) -> list[Review]:
    query = (
        select(Review)
        .where(Review.user_id == user_id, Review.completed_at.is_(None))
        .order_by(Review.scheduled_for)
        .limit(limit)
    )
    if not include_upcoming:
        query = query.where(Review.scheduled_for <= utcnow())
    return list(db.scalars(query).all())


def complete_review(
    db: Session, user_id: uuid.UUID, review_id: uuid.UUID, outcome: str = "recalled"
) -> Review:
    """Close a review and schedule the next one based on the outcome."""
    from app.gamification.streaks import record_activity, user_timezone
    from app.gamification.xp import award_xp, bonus_key, rules_for
    from app.utils.timeutils import local_date

    review = db.scalar(
        select(Review).where(Review.id == review_id, Review.user_id == user_id)
    )
    if review is None:
        raise NotFoundError("Review not found")

    now = utcnow()
    review.completed_at = now
    review.outcome = outcome

    user_problem = db.scalar(
        select(UserProblem).where(
            UserProblem.user_id == user_id, UserProblem.problem_id == review.problem_id
        )
    )
    if user_problem is not None:
        user_problem.review_count += 1

    if outcome == "recalled":
        interval = next_interval(review.interval_days)
        # Three clean recalls at the longest interval means it is genuinely
        # retained — stop nagging and mark it mastered.
        if (
            interval >= REVIEW_INTERVALS[-1]
            and user_problem is not None
            and user_problem.review_count >= 3
        ):
            user_problem.needs_review = False
            user_problem.review_due_at = None
            if user_problem.status == ProblemStatus.SOLVED:
                user_problem.status = ProblemStatus.MASTERED
        else:
            _upsert_review(
                db,
                user_id,
                review.problem_id,
                ReviewReason.STALE,
                "Scheduled follow-up after a successful recall.",
                interval,
            )
    else:
        # Forgotten or partial: back to the shortest interval.
        _upsert_review(
            db,
            user_id,
            review.problem_id,
            ReviewReason.REPEATED_MISTAKE,
            "You did not fully recall this on review.",
            REVIEW_INTERVALS[0],
        )
        if user_problem is not None:
            user_problem.status = ProblemStatus.REVISIT

    tz = user_timezone(db, user_id)
    day = local_date(now, tz)
    record_activity(db, user_id, day, reviews_completed=1)
    rules = rules_for(db, user_id)
    award_xp(
        db,
        user_id,
        amount=rules.bonus_for("review_completed"),
        kind=XPKind.BONUS,
        reason="Completed a review",
        dedupe_key=bonus_key("review", str(review.id)),
        activity_date=day,
    )

    db.commit()
    db.refresh(review)
    return review


def count_due(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count(Review.id)).where(
                Review.user_id == user_id,
                Review.completed_at.is_(None),
                Review.scheduled_for <= utcnow(),
            )
        )
        or 0
    )


def refresh_stale_reviews(db: Session, user_id: uuid.UUID, days: int = 60) -> int:
    """Queue long-untouched core-pattern problems for a refresher."""
    cutoff = utcnow() - timedelta(days=days)
    candidates = db.scalars(
        select(UserProblem)
        .join(Problem, Problem.id == UserProblem.problem_id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status.in_((ProblemStatus.SOLVED, ProblemStatus.REVISIT)),
            UserProblem.last_solved_at < cutoff,
            UserProblem.needs_review.is_(False),
        )
        .limit(20)
    ).all()

    queued = 0
    for user_problem in candidates:
        if _is_core_pattern(db, user_problem.problem_id):
            _upsert_review(
                db,
                user_id,
                user_problem.problem_id,
                ReviewReason.STALE,
                f"Core pattern not revisited in {days}+ days.",
                1,
            )
            queued += 1
    if queued:
        db.commit()
    return queued
