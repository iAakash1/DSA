"""Recording solves and attempts.

This is the spine of the application: one call updates the submission history,
problem status, activity day, XP ledger, streak, missions, review schedule and
achievements — consistently, and idempotently.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.models.enums import (
    MistakeType,
    Platform,
    ProblemStatus,
    SolutionSource,
    SubmissionSource,
    XPKind,
)
from app.models.gamification import DailyGoal, UserStats
from app.models.problem import Problem, ProblemTopic, Topic
from app.models.progress import Mistake, SolvingSession, Submission, UserProblem
from app.gamification.achievements import evaluate_achievements
from app.gamification.streaks import (
    check_streak_milestone,
    record_activity,
    roll_over_streak,
    user_timezone,
)
from app.gamification.xp import award_xp, bonus_key, first_solve_key, rules_for, total_xp
from app.services.problem_service import get_user_problem, require_problem
from app.utils.timeutils import local_date, today_in, utcnow

log = get_logger(__name__)

#: Independence ordering — a later solve never downgrades a recorded best.
_SOURCE_STRENGTH = {
    SolutionSource.COPIED: 0,
    SolutionSource.DISCUSSION: 1,
    SolutionSource.EDITORIAL: 2,
    SolutionSource.HINT: 3,
    SolutionSource.INDEPENDENT: 4,
    #: Unranked: any explicit report replaces it, in either direction.
    SolutionSource.UNKNOWN: -1,
}


def _better_source(current: str | None, incoming: str) -> str:
    """Pick the source to keep on `UserProblem.best_solution_source`.

    An explicit report always beats `unknown`, even a worse one — the user
    telling us they copied it is more informative than a sync's silence.
    """
    if current is None or current == SolutionSource.UNKNOWN:
        return incoming
    if incoming == SolutionSource.UNKNOWN:
        return current
    return max((current, incoming), key=lambda s: _SOURCE_STRENGTH.get(s, -1))


@dataclass
class SolveResult:
    problem_id: uuid.UUID
    first_solve: bool
    xp_awarded: int = 0
    xp_breakdown: dict[str, int] = field(default_factory=dict)
    streak: int = 0
    longest_streak: int = 0
    level_before: int = 1
    level_after: int = 1
    leveled_up: bool = False
    achievements_unlocked: list[str] = field(default_factory=list)
    daily_goal_progress: int = 0
    daily_goal_target: int = 0
    activity_date: date | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "problem_id": str(self.problem_id),
            "first_solve": self.first_solve,
            "xp_awarded": self.xp_awarded,
            "xp_breakdown": self.xp_breakdown,
            "streak": self.streak,
            "longest_streak": self.longest_streak,
            "leveled_up": self.leveled_up,
            "level": self.level_after,
            "achievements_unlocked": self.achievements_unlocked,
            "daily_goal": {
                "progress": self.daily_goal_progress,
                "target": self.daily_goal_target,
            },
            "activity_date": self.activity_date.isoformat() if self.activity_date else None,
        }


def record_solve(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    *,
    solved_at: datetime | None = None,
    solution_source: str = SolutionSource.INDEPENDENT,
    time_spent_seconds: int | None = None,
    attempt_count: int = 1,
    confidence: int | None = None,
    difficulty_perception: int | None = None,
    notes: str | None = None,
    approach: str | None = None,
    mistakes: list[str] | None = None,
    external_submission_id: str | None = None,
    submission_source: str = SubmissionSource.MANUAL,
    during_contest: bool = False,
    external_contest_id: str | None = None,
    language: str | None = None,
    create_session: bool = True,
    commit: bool = True,
    defer_aggregates: bool = False,
) -> SolveResult:
    """Record an accepted solve and cascade every downstream effect.

    `defer_aggregates` skips the per-solve rollups (streak, missions, reviews,
    achievements) for bulk ingestion. Callers using it MUST finish by calling
    `recompute_user_state`, which produces the same end state in one pass
    instead of N.
    """
    problem = require_problem(db, problem_id)
    solved_at = solved_at or utcnow()
    tz = user_timezone(db, user_id)
    day = local_date(solved_at, tz)

    if solution_source not in _SOURCE_STRENGTH:
        raise ValidationError(f"Unknown solution source {solution_source!r}")

    level_before = _current_level(db, user_id)

    submission = _record_submission(
        db,
        user_id,
        problem,
        submitted_at=solved_at,
        verdict="OK" if problem.platform == Platform.CODEFORCES else "Accepted",
        is_accepted=True,
        external_submission_id=external_submission_id,
        source=submission_source,
        language=language,
        during_contest=during_contest,
        external_contest_id=external_contest_id,
    )
    submission_is_new = submission is not None

    user_problem = get_user_problem(db, user_id, problem_id)
    first_solve = user_problem.first_solved_at is None

    user_problem.attempts = max(user_problem.attempts, 0) + max(1, attempt_count)
    user_problem.solved_count += 1
    user_problem.last_solved_at = solved_at
    user_problem.last_attempted_at = solved_at
    if first_solve:
        user_problem.first_solved_at = solved_at
    if user_problem.status in (ProblemStatus.UNSOLVED, ProblemStatus.ATTEMPTED, ProblemStatus.SKIPPED):
        user_problem.status = ProblemStatus.SOLVED
    if confidence is not None:
        user_problem.confidence = confidence
    if time_spent_seconds:
        user_problem.total_time_seconds += max(0, time_spent_seconds)

    user_problem.best_solution_source = _better_source(
        user_problem.best_solution_source, solution_source
    )

    if create_session:
        db.add(
            SolvingSession(
                user_id=user_id,
                problem_id=problem_id,
                started_at=None,
                finished_at=solved_at,
                time_spent_seconds=time_spent_seconds,
                attempt_count=max(1, attempt_count),
                result="solved",
                solution_source=solution_source,
                confidence=confidence,
                difficulty_perception=difficulty_perception,
                notes=notes,
                approach=approach,
            )
        )

    if mistakes:
        _record_mistakes(db, user_id, problem_id, mistakes, solved_at)

    db.flush()

    xp_breakdown: dict[str, int] = {}
    rules = rules_for(db, user_id)

    if first_solve:
        base = rules.for_problem(problem.platform, problem.difficulty, problem.rating)
        granted = award_xp(
            db,
            user_id,
            amount=base,
            kind=XPKind.FIRST_SOLVE,
            reason=f"Solved {problem.title}",
            dedupe_key=first_solve_key(problem_id),
            activity_date=day,
            problem_id=problem_id,
        )
        if granted:
            xp_breakdown["solve"] = granted

    topics = _topic_slugs(db, problem_id)
    record_activity(
        db,
        user_id,
        day,
        problems_solved=1 if first_solve else 0,
        submissions=1 if submission_is_new else 0,
        minutes_spent=(time_spent_seconds or 0) // 60,
        upsolves=1 if (during_contest is False and external_contest_id) else 0,
        topics=topics,
    )

    if defer_aggregates:
        _sync_activity_xp(db, user_id, day)
        if commit:
            db.commit()
        return SolveResult(
            problem_id=problem_id,
            first_solve=first_solve,
            xp_awarded=sum(xp_breakdown.values()),
            xp_breakdown=xp_breakdown,
            activity_date=day,
        )

    if first_solve:
        xp_breakdown.update(
            _award_solve_bonuses(db, user_id, problem, day, solution_source)
        )

    goal_progress, goal_target = _update_daily_goal(db, user_id, day)
    if goal_progress >= goal_target > 0:
        granted = award_xp(
            db,
            user_id,
            amount=rules.bonus_for("daily_goal_completed"),
            kind=XPKind.BONUS,
            reason="Daily goal completed",
            dedupe_key=bonus_key("daily_goal", day.isoformat()),
            activity_date=day,
        )
        if granted:
            xp_breakdown["daily_goal"] = granted

    # Missions advance on first solves only. Counting re-solves would let the
    # same problem be solved twice to clear "solve 2 problems", and would
    # disagree with `activity_days.problems_solved`, which counts distinct
    # problems.
    if first_solve:
        from app.services.mission_service import update_mission_progress

        xp_breakdown.update(update_mission_progress(db, user_id, problem, day))

    _sync_activity_xp(db, user_id, day)
    db.flush()

    state = roll_over_streak(db, user_id)
    milestone_xp = check_streak_milestone(db, user_id, state.current, day)
    if milestone_xp:
        xp_breakdown["streak_milestone"] = milestone_xp
        _sync_activity_xp(db, user_id, day)

    from app.services.review_service import schedule_review_after_solve

    schedule_review_after_solve(
        db,
        user_id,
        problem_id,
        solution_source=solution_source,
        confidence=confidence,
        attempts=user_problem.attempts,
        mistakes=mistakes or [],
    )

    unlocked = evaluate_achievements(db, user_id)
    _refresh_user_stats(db, user_id)

    level_after = _current_level(db, user_id)
    if commit:
        db.commit()

    result = SolveResult(
        problem_id=problem_id,
        first_solve=first_solve,
        xp_awarded=sum(xp_breakdown.values()),
        xp_breakdown=xp_breakdown,
        streak=state.current,
        longest_streak=state.longest,
        level_before=level_before,
        level_after=level_after,
        leveled_up=level_after > level_before,
        achievements_unlocked=[a.code for a in unlocked],
        daily_goal_progress=goal_progress,
        daily_goal_target=goal_target,
        activity_date=day,
    )
    log.info(
        "solve recorded",
        user_id=str(user_id),
        problem=problem.canonical_id,
        first_solve=first_solve,
        xp=result.xp_awarded,
        streak=result.streak,
    )
    return result


def record_attempt(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    *,
    attempted_at: datetime | None = None,
    verdict: str = "WRONG_ANSWER",
    time_spent_seconds: int | None = None,
    notes: str | None = None,
    mistakes: list[str] | None = None,
    external_submission_id: str | None = None,
    submission_source: str = SubmissionSource.MANUAL,
    language: str | None = None,
    commit: bool = True,
) -> UserProblem:
    """Record a failed attempt. No XP, but the history matters for analytics."""
    problem = require_problem(db, problem_id)
    attempted_at = attempted_at or utcnow()
    tz = user_timezone(db, user_id)
    day = local_date(attempted_at, tz)

    _record_submission(
        db,
        user_id,
        problem,
        submitted_at=attempted_at,
        verdict=verdict,
        is_accepted=False,
        external_submission_id=external_submission_id,
        source=submission_source,
        language=language,
    )

    user_problem = get_user_problem(db, user_id, problem_id)
    user_problem.attempts += 1
    user_problem.last_attempted_at = attempted_at
    if user_problem.status == ProblemStatus.UNSOLVED:
        user_problem.status = ProblemStatus.ATTEMPTED
    if time_spent_seconds:
        user_problem.total_time_seconds += max(0, time_spent_seconds)

    db.add(
        SolvingSession(
            user_id=user_id,
            problem_id=problem_id,
            finished_at=attempted_at,
            time_spent_seconds=time_spent_seconds,
            attempt_count=1,
            result="failed",
            solution_source=SolutionSource.INDEPENDENT,
            notes=notes,
        )
    )
    if mistakes:
        _record_mistakes(db, user_id, problem_id, mistakes, attempted_at)

    record_activity(db, user_id, day, submissions=1)
    if commit:
        db.commit()
    return user_problem


def set_status(
    db: Session, user_id: uuid.UUID, problem_id: uuid.UUID, status: str
) -> UserProblem:
    """Manually set a problem's status.

    Marking something solved here goes through `record_solve` so XP, activity
    and achievements stay consistent — and un-marking never claws XP back,
    because the ledger is append-only and the dedupe key persists.
    """
    if status not in tuple(ProblemStatus):
        raise ValidationError(f"Unknown status {status!r}")

    user_problem = get_user_problem(db, user_id, problem_id)
    if status in (ProblemStatus.SOLVED, ProblemStatus.MASTERED) and (
        user_problem.first_solved_at is None
    ):
        record_solve(db, user_id, problem_id, solution_source=SolutionSource.INDEPENDENT)
        user_problem = get_user_problem(db, user_id, problem_id)

    user_problem.status = status
    if status == ProblemStatus.REVISIT:
        user_problem.needs_review = True
    db.commit()
    db.refresh(user_problem)
    return user_problem


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _record_submission(
    db: Session,
    user_id: uuid.UUID,
    problem: Problem,
    *,
    submitted_at: datetime,
    verdict: str,
    is_accepted: bool,
    external_submission_id: str | None,
    source: str,
    language: str | None = None,
    runtime_ms: int | None = None,
    memory_kb: int | None = None,
    during_contest: bool = False,
    external_contest_id: str | None = None,
) -> Submission | None:
    """Insert a submission, skipping platform duplicates.

    Returns None when the submission was already recorded — which is what makes
    re-running a sync free of side effects.
    """
    if external_submission_id:
        existing = db.scalar(
            select(Submission).where(
                Submission.user_id == user_id,
                Submission.platform == problem.platform,
                Submission.external_submission_id == external_submission_id,
            )
        )
        if existing is not None:
            return None

    submission = Submission(
        user_id=user_id,
        problem_id=problem.id,
        platform=problem.platform,
        external_submission_id=external_submission_id,
        submitted_at=submitted_at,
        verdict=verdict,
        is_accepted=is_accepted,
        language=language,
        runtime_ms=runtime_ms,
        memory_kb=memory_kb,
        source=source,
        during_contest=during_contest,
        external_contest_id=external_contest_id,
    )
    try:
        with db.begin_nested():
            db.add(submission)
    except IntegrityError:
        return None
    return submission


def _record_mistakes(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    mistakes: list[str],
    occurred_at: datetime,
) -> None:
    valid = {m.value for m in MistakeType}
    for mistake_type in mistakes:
        if mistake_type not in valid:
            raise ValidationError(f"Unknown mistake type {mistake_type!r}")
        db.add(
            Mistake(
                user_id=user_id,
                problem_id=problem_id,
                mistake_type=mistake_type,
                occurred_at=occurred_at,
            )
        )
    db.flush()


def _topic_slugs(db: Session, problem_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(Topic.slug)
            .join(ProblemTopic, ProblemTopic.topic_id == Topic.id)
            .where(ProblemTopic.problem_id == problem_id)
        ).all()
    )


def _award_solve_bonuses(
    db: Session,
    user_id: uuid.UUID,
    problem: Problem,
    day: date,
    solution_source: str,
) -> dict[str, int]:
    """Bonuses that only apply to a genuine first solve."""
    from app.models.gamification import ActivityDay

    rules = rules_for(db, user_id)
    breakdown: dict[str, int] = {}

    activity = db.scalar(
        select(ActivityDay).where(
            ActivityDay.user_id == user_id, ActivityDay.activity_date == day
        )
    )
    if activity and activity.problems_solved == 1:
        granted = award_xp(
            db,
            user_id,
            amount=rules.bonus_for("first_problem_of_day"),
            kind=XPKind.BONUS,
            reason="First problem of the day",
            dedupe_key=bonus_key("first_of_day", day.isoformat()),
            activity_date=day,
        )
        if granted:
            breakdown["first_of_day"] = granted

    # Solving above your recent average is the behaviour worth reinforcing.
    if (
        problem.rating
        and problem.platform == Platform.CODEFORCES
        and solution_source == SolutionSource.INDEPENDENT
    ):
        average = _average_solved_rating(db, user_id)
        if average and problem.rating >= average + 100:
            granted = award_xp(
                db,
                user_id,
                amount=rules.bonus_for("above_average_difficulty"),
                kind=XPKind.BONUS,
                reason=f"Solved {problem.rating} — above your {int(average)} average",
                dedupe_key=bonus_key("above_average", str(problem.id)),
                activity_date=day,
                problem_id=problem.id,
            )
            if granted:
                breakdown["above_average"] = granted

    return breakdown


def _average_solved_rating(db: Session, user_id: uuid.UUID) -> float | None:
    value = db.scalar(
        select(func.avg(Problem.rating))
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.first_solved_at.is_not(None),
            Problem.rating.is_not(None),
        )
    )
    return float(value) if value is not None else None


def _update_daily_goal(db: Session, user_id: uuid.UUID, day: date) -> tuple[int, int]:
    from app.models.gamification import ActivityDay
    from app.models.user import UserSettings

    config = db.get(UserSettings, user_id)
    target = config.daily_goal if config else 2

    goal = db.scalar(
        select(DailyGoal).where(DailyGoal.user_id == user_id, DailyGoal.goal_date == day)
    )
    if goal is None:
        goal = DailyGoal(user_id=user_id, goal_date=day, target=target)
        db.add(goal)

    solved_today = int(
        db.scalar(
            select(func.coalesce(func.sum(ActivityDay.problems_solved), 0)).where(
                ActivityDay.user_id == user_id, ActivityDay.activity_date == day
            )
        )
        or 0
    )
    goal.progress = solved_today
    goal.target = target
    if solved_today >= target and goal.completed_at is None:
        goal.completed_at = utcnow()
    db.flush()
    return solved_today, target


def _sync_activity_xp(db: Session, user_id: uuid.UUID, day: date) -> None:
    """Keep `activity_days.xp_earned` equal to the ledger for that day."""
    from app.gamification.xp import xp_on_date
    from app.models.gamification import ActivityDay

    activity = db.scalar(
        select(ActivityDay).where(
            ActivityDay.user_id == user_id, ActivityDay.activity_date == day
        )
    )
    if activity is not None:
        activity.xp_earned = xp_on_date(db, user_id, day)
        db.flush()


def _current_level(db: Session, user_id: uuid.UUID) -> int:
    from app.gamification.xp import level_info

    return level_info(db, user_id).level


def _refresh_user_stats(db: Session, user_id: uuid.UUID) -> None:
    stats = db.get(UserStats, user_id)
    if stats is None:
        stats = UserStats(user_id=user_id)
        db.add(stats)

    solved_statuses = (
        ProblemStatus.SOLVED,
        ProblemStatus.MASTERED,
        ProblemStatus.REVISIT,
    )
    stats.total_xp = total_xp(db, user_id)
    stats.level = _current_level(db, user_id)
    stats.problems_solved = int(
        db.scalar(
            select(func.count(UserProblem.id)).where(
                UserProblem.user_id == user_id,
                UserProblem.status.in_(solved_statuses),
            )
        )
        or 0
    )
    stats.independent_solves = int(
        db.scalar(
            select(func.count(UserProblem.id)).where(
                UserProblem.user_id == user_id,
                UserProblem.status.in_(solved_statuses),
                UserProblem.best_solution_source == SolutionSource.INDEPENDENT,
            )
        )
        or 0
    )
    stats.last_recomputed_at = utcnow()
    db.flush()


def recompute_user_state(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Rebuild every derived aggregate in one pass.

    Used after bulk ingestion (platform sync, imports) and available as a
    repair operation — every number here is derivable from the raw rows, so
    this can always restore a consistent state.
    """
    from app.gamification.xp import xp_on_date
    from app.models.gamification import ActivityDay

    days = db.scalars(
        select(ActivityDay.activity_date).where(ActivityDay.user_id == user_id)
    ).all()
    for day in days:
        activity = db.scalar(
            select(ActivityDay).where(
                ActivityDay.user_id == user_id, ActivityDay.activity_date == day
            )
        )
        if activity is not None:
            activity.xp_earned = xp_on_date(db, user_id, day)
    db.flush()

    state = roll_over_streak(db, user_id)
    unlocked = evaluate_achievements(db, user_id)
    _refresh_user_stats(db, user_id)
    db.commit()

    return {
        "streak": state.current,
        "longest_streak": state.longest,
        "achievements_unlocked": [a.code for a in unlocked],
        "activity_days": len(days),
    }


def today_for(db: Session, user_id: uuid.UUID) -> date:
    return today_in(user_timezone(db, user_id))
