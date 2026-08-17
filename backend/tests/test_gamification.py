"""XP, levels, streaks and freezes.

These encode the rules that make the gamification honest: XP cannot be farmed,
streaks respect the user's timezone, and a freeze is a recorded transaction
rather than a silent history rewrite.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.gamification.rules import level_for_xp, resolve_rules
from app.gamification.streaks import (
    compute_streak,
    freeze_balance,
    purchase_freeze,
    record_activity,
    roll_over_streak,
)
from app.gamification.xp import award_xp, first_solve_key, total_xp
from app.models.enums import Difficulty, Platform, ProblemStatus, SolutionSource, XPKind
from app.models.user import UserSettings
from app.services.solve_service import record_solve
from app.utils.timeutils import local_date, today_in


# ---------------------------------------------------------------------------
# XP rules
# ---------------------------------------------------------------------------


def test_leetcode_xp_by_difficulty():
    rules = resolve_rules()
    assert rules.for_problem(Platform.LEETCODE, Difficulty.EASY, None) == 10
    assert rules.for_problem(Platform.LEETCODE, Difficulty.MEDIUM, None) == 20
    assert rules.for_problem(Platform.LEETCODE, Difficulty.HARD, None) == 40


@pytest.mark.parametrize(
    "rating,expected",
    [(800, 10), (999, 10), (1000, 15), (1200, 20), (1400, 30), (1600, 40), (1800, 60), (2400, 60)],
)
def test_codeforces_xp_bands(rating, expected):
    rules = resolve_rules()
    assert rules.for_problem(Platform.CODEFORCES, Difficulty.UNKNOWN, rating) == expected


def test_unrated_codeforces_problem_still_awards_entry_band():
    rules = resolve_rules()
    assert rules.for_problem(Platform.CODEFORCES, Difficulty.UNKNOWN, None) == 10


def test_xp_rules_are_configurable():
    rules = resolve_rules({"leetcode": {"easy": 99}, "bonus": {"upsolve": 7}})
    assert rules.for_problem(Platform.LEETCODE, Difficulty.EASY, None) == 99
    assert rules.bonus_for("upsolve") == 7


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------


def test_level_one_starts_at_zero_xp():
    info = level_for_xp(0)
    assert info.level == 1
    assert info.xp_into_level == 0


def test_levels_increase_monotonically():
    levels = [level_for_xp(xp).level for xp in (0, 500, 2000, 8000, 30000)]
    assert levels == sorted(levels)
    assert len(set(levels)) > 1


def test_level_progress_is_bounded():
    for xp in (0, 123, 5000, 999_999):
        info = level_for_xp(xp)
        assert 0.0 <= info.progress <= 1.0


def test_max_level_reports_no_next_level():
    info = level_for_xp(10_000_000)
    assert info.xp_to_next_level is None
    assert info.progress == 1.0


# ---------------------------------------------------------------------------
# XP ledger — the anti-exploit guarantees
# ---------------------------------------------------------------------------


def test_duplicate_dedupe_key_awards_once(db, user):
    today = today_in(user.timezone)
    key = "test:duplicate"

    first = award_xp(db, user.id, amount=25, kind=XPKind.BONUS, reason="first",
                     dedupe_key=key, activity_date=today, commit=True)
    second = award_xp(db, user.id, amount=25, kind=XPKind.BONUS, reason="again",
                      dedupe_key=key, activity_date=today, commit=True)

    assert first == 25
    assert second == 0
    assert total_xp(db, user.id) == 25


def test_resolving_a_problem_awards_no_additional_first_solve_xp(db, user, make_problem):
    problem = make_problem("1500A", rating=1500)

    first = record_solve(db, user.id, problem.id, solution_source=SolutionSource.INDEPENDENT)
    after_first = total_xp(db, user.id)
    assert first.first_solve is True
    assert first.xp_breakdown.get("solve") == 30

    second = record_solve(db, user.id, problem.id, solution_source=SolutionSource.INDEPENDENT)

    assert second.first_solve is False
    assert "solve" not in second.xp_breakdown
    assert total_xp(db, user.id) == after_first


def test_first_solve_key_is_stable(make_problem):
    problem = make_problem("1600C")
    assert first_solve_key(problem.id) == f"first_solve:{problem.id}"


def test_negative_and_zero_awards_are_ignored(db, user):
    today = today_in(user.timezone)
    assert award_xp(db, user.id, amount=0, kind=XPKind.BONUS, reason="zero",
                    dedupe_key="z", activity_date=today) == 0
    assert award_xp(db, user.id, amount=-50, kind=XPKind.BONUS, reason="neg",
                    dedupe_key="n", activity_date=today) == 0


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------


def _activity_on(db, user, day: date, problems: int = 1):
    record_activity(db, user.id, day, problems_solved=problems)
    db.commit()


def test_single_day_gives_streak_of_one(db, user):
    _activity_on(db, user, today_in(user.timezone))
    assert compute_streak(db, user.id, user.timezone).current == 1


def test_consecutive_days_accumulate(db, user):
    today = today_in(user.timezone)
    for offset in range(3):
        _activity_on(db, user, today - timedelta(days=offset))
    assert compute_streak(db, user.id, user.timezone).current == 3


def test_gap_breaks_the_streak(db, user):
    today = today_in(user.timezone)
    _activity_on(db, user, today - timedelta(days=5))
    _activity_on(db, user, today - timedelta(days=4))
    # Nothing since; the run ended days ago.
    assert compute_streak(db, user.id, user.timezone).current == 0


def test_inactive_today_does_not_break_a_live_streak(db, user):
    """Today is not over yet, so yesterday's streak still stands."""
    today = today_in(user.timezone)
    _activity_on(db, user, today - timedelta(days=1))
    _activity_on(db, user, today - timedelta(days=2))

    state = compute_streak(db, user.id, user.timezone)
    assert state.current == 2
    assert state.active_today is False


def test_longest_streak_is_remembered_after_a_break(db, user):
    today = today_in(user.timezone)
    for offset in range(20, 15, -1):  # a 5-day run long ago
        _activity_on(db, user, today - timedelta(days=offset))
    _activity_on(db, user, today)

    state = compute_streak(db, user.id, user.timezone)
    assert state.current == 1
    assert state.longest == 5


# ---------------------------------------------------------------------------
# Streak freezes
# ---------------------------------------------------------------------------


def test_freeze_purchase_requires_enough_xp(db, user):
    result = purchase_freeze(db, user.id)
    assert result["purchased"] is False
    assert "XP" in result["reason"]


def test_freeze_purchase_deducts_xp_and_grants_one(db, user):
    today = today_in(user.timezone)
    award_xp(db, user.id, amount=1000, kind=XPKind.BONUS, reason="seed",
             dedupe_key="seed", activity_date=today, commit=True)

    result = purchase_freeze(db, user.id)

    assert result["purchased"] is True
    assert result["balance"] == 1
    assert total_xp(db, user.id) == 500  # 1000 - 500 cost


def test_freeze_respects_maximum_balance(db, user):
    today = today_in(user.timezone)
    award_xp(db, user.id, amount=10_000, kind=XPKind.BONUS, reason="seed",
             dedupe_key="seed-max", activity_date=today, commit=True)

    config = db.get(UserSettings, user.id)
    for _ in range(config.max_freezes):
        assert purchase_freeze(db, user.id)["purchased"] is True

    blocked = purchase_freeze(db, user.id)
    assert blocked["purchased"] is False
    assert "maximum" in blocked["reason"]


def test_freeze_protects_a_missed_day_and_is_consumed(db, user):
    today = today_in(user.timezone)
    award_xp(db, user.id, amount=1000, kind=XPKind.BONUS, reason="seed",
             dedupe_key="seed-freeze", activity_date=today, commit=True)
    purchase_freeze(db, user.id)
    assert freeze_balance(db, user.id) == 1

    # Active two days ago, nothing yesterday: yesterday is the gap.
    _activity_on(db, user, today - timedelta(days=2))

    state = roll_over_streak(db, user.id)

    assert freeze_balance(db, user.id) == 0, "the freeze should have been spent"
    assert state.current == 2, "the frozen day keeps the run alive"


def test_gap_larger_than_balance_is_not_partially_frozen(db, user):
    """Spending a freeze on a gap it cannot cover would waste it."""
    today = today_in(user.timezone)
    award_xp(db, user.id, amount=1000, kind=XPKind.BONUS, reason="seed",
             dedupe_key="seed-gap", activity_date=today, commit=True)
    purchase_freeze(db, user.id)

    _activity_on(db, user, today - timedelta(days=5))  # a 4-day hole

    state = roll_over_streak(db, user.id)

    assert freeze_balance(db, user.id) == 1, "freeze retained"
    assert state.current == 0


# ---------------------------------------------------------------------------
# Timezone correctness
# ---------------------------------------------------------------------------


def test_local_date_differs_from_utc_date_across_the_dateline():
    """A solve at 20:00 UTC is already tomorrow in Asia/Kolkata (+05:30)."""
    moment = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)

    assert local_date(moment, "UTC") == date(2026, 3, 10)
    assert local_date(moment, "Asia/Kolkata") == date(2026, 3, 11)
    assert local_date(moment, "America/Los_Angeles") == date(2026, 3, 10)


def test_solve_is_bucketed_by_the_users_timezone(db, user, make_problem):
    """The same instant must land on different activity days per timezone."""
    problem = make_problem("1700D", rating=1700)
    user.timezone = "Asia/Kolkata"
    db.commit()

    moment = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
    result = record_solve(db, user.id, problem.id, solved_at=moment)

    assert result.activity_date == date(2026, 3, 11)


def test_unknown_timezone_falls_back_without_raising(db, user, make_problem):
    user.timezone = "Not/AZone"
    db.commit()
    problem = make_problem("1234E", rating=1000)
    # Must not raise — a bad timezone cannot break the dashboard.
    assert record_solve(db, user.id, problem.id).activity_date is not None


# ---------------------------------------------------------------------------
# Solve bookkeeping
# ---------------------------------------------------------------------------


def test_solve_marks_status_and_records_history(db, user, make_problem):
    problem = make_problem("1111A", rating=1100)
    record_solve(db, user.id, problem.id, time_spent_seconds=600, confidence=4)

    from app.services.problem_service import get_user_problem

    up = get_user_problem(db, user.id, problem.id)
    assert up.status == ProblemStatus.SOLVED
    assert up.first_solved_at is not None
    assert up.total_time_seconds == 600
    assert up.confidence == 4


def test_explicit_report_replaces_unknown_source(db, user, make_problem):
    """A sync records `unknown`; a later self-report must win."""
    problem = make_problem("1222B", rating=1200)

    record_solve(db, user.id, problem.id, solution_source=SolutionSource.UNKNOWN)
    from app.services.problem_service import get_user_problem

    assert get_user_problem(db, user.id, problem.id).best_solution_source == SolutionSource.UNKNOWN

    record_solve(db, user.id, problem.id, solution_source=SolutionSource.EDITORIAL)
    assert get_user_problem(db, user.id, problem.id).best_solution_source == SolutionSource.EDITORIAL


def test_stronger_source_upgrades_but_weaker_does_not_downgrade(db, user, make_problem):
    problem = make_problem("1333C", rating=1300)
    from app.services.problem_service import get_user_problem

    record_solve(db, user.id, problem.id, solution_source=SolutionSource.EDITORIAL)
    record_solve(db, user.id, problem.id, solution_source=SolutionSource.INDEPENDENT)
    assert get_user_problem(db, user.id, problem.id).best_solution_source == SolutionSource.INDEPENDENT

    record_solve(db, user.id, problem.id, solution_source=SolutionSource.COPIED)
    assert get_user_problem(db, user.id, problem.id).best_solution_source == SolutionSource.INDEPENDENT


# ---------------------------------------------------------------------------
# Regression: transaction isolation of duplicate bonuses
# ---------------------------------------------------------------------------


def test_many_solves_in_one_day_all_persist(db, user, make_problem):
    """Regression: a duplicate daily bonus must not roll back the solve.

    Bonuses like `daily_goal` are deduped by a unique key. That INSERT failing
    on the 3rd+ solve of a day previously rolled back the whole transaction,
    silently discarding the solve. Each award now runs in its own savepoint.
    """
    problems = [make_problem(f"999{i}A", rating=1000) for i in range(5)]

    for problem in problems:
        record_solve(db, user.id, problem.id)

    from app.services.problem_service import get_user_problem

    solved = [
        get_user_problem(db, user.id, p.id, create=False) for p in problems
    ]
    assert all(up is not None and up.first_solved_at is not None for up in solved), (
        "every solve must survive, not just the ones before the first duplicate bonus"
    )

    today = today_in(user.timezone)
    from app.models.gamification import ActivityDay
    from sqlalchemy import select as _select

    activity = db.scalar(
        _select(ActivityDay).where(
            ActivityDay.user_id == user.id, ActivityDay.activity_date == today
        )
    )
    assert activity.problems_solved == 5


def test_duplicate_daily_bonus_is_awarded_only_once(db, user, make_problem):
    for i in range(4):
        record_solve(db, user.id, make_problem(f"998{i}A", rating=1000).id)

    from app.models.gamification import XPTransaction
    from sqlalchemy import func as _func, select as _select

    daily_goal_awards = db.scalar(
        _select(_func.count(XPTransaction.id)).where(
            XPTransaction.user_id == user.id,
            XPTransaction.reason == "Daily goal completed",
        )
    )
    assert daily_goal_awards == 1
