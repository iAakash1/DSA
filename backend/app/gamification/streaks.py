"""Streaks, activity days and streak freezes.

Correctness rules that this module exists to enforce:

* A "day" is a calendar day in the *user's* timezone, never a UTC date.
* A streak survives a gap only when a freeze is actually consumed, and the
  consumption is recorded as a transaction. History is never silently edited.
* Today is never treated as a missed day — it is not over yet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import FreezeKind, XPKind
from app.models.gamification import (
    ActivityDay,
    StreakFreezeTransaction,
    UserStats,
)
from app.models.user import Profile, UserSettings
from app.gamification.xp import spend_xp, total_xp
from app.utils.timeutils import today_in

log = get_logger(__name__)

#: Freezes can only be applied retroactively within this window. Without a
#: bound, a user returning after six months would revive a dead streak.
MAX_FREEZE_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class StreakState:
    current: int
    longest: int
    last_active_date: date | None
    freezes_available: int
    active_today: bool


def user_timezone(db: Session, user_id: uuid.UUID) -> str:
    profile = db.get(Profile, user_id)
    return profile.timezone if profile else "UTC"


# ---------------------------------------------------------------------------
# Activity days
# ---------------------------------------------------------------------------


def get_or_create_activity_day(
    db: Session, user_id: uuid.UUID, day: date
) -> ActivityDay:
    row = db.scalar(
        select(ActivityDay).where(
            ActivityDay.user_id == user_id, ActivityDay.activity_date == day
        )
    )
    if row is None:
        # Savepoint: a concurrent insert must not discard the caller's work.
        try:
            with db.begin_nested():
                row = ActivityDay(user_id=user_id, activity_date=day)
                db.add(row)
        except IntegrityError:
            row = db.scalar(
                select(ActivityDay).where(
                    ActivityDay.user_id == user_id, ActivityDay.activity_date == day
                )
            )
    return row


def record_activity(
    db: Session,
    user_id: uuid.UUID,
    day: date,
    *,
    problems_solved: int = 0,
    xp_earned: int = 0,
    minutes_spent: int = 0,
    submissions: int = 0,
    contests: int = 0,
    upsolves: int = 0,
    reviews_completed: int = 0,
    topics: list[str] | None = None,
) -> ActivityDay:
    """Add activity to a local calendar day."""
    row = get_or_create_activity_day(db, user_id, day)
    row.problems_solved += problems_solved
    row.xp_earned += xp_earned
    row.minutes_spent += minutes_spent
    row.submissions += submissions
    row.contests += contests
    row.upsolves += upsolves
    row.reviews_completed += reviews_completed
    if topics:
        row.topics_touched = sorted({*(row.topics_touched or []), *topics})
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Freezes
# ---------------------------------------------------------------------------


def freeze_balance(db: Session, user_id: uuid.UUID) -> int:
    rows = db.execute(
        select(
            StreakFreezeTransaction.kind,
            func.coalesce(func.sum(StreakFreezeTransaction.amount), 0),
        )
        .where(StreakFreezeTransaction.user_id == user_id)
        .group_by(StreakFreezeTransaction.kind)
    ).all()
    totals = {kind: int(amount) for kind, amount in rows}
    gained = totals.get(FreezeKind.EARNED, 0) + totals.get(FreezeKind.PURCHASED, 0)
    spent = totals.get(FreezeKind.USED, 0) + totals.get(FreezeKind.EXPIRED, 0)
    return max(0, gained - spent)


def _record_freeze(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: str,
    amount: int,
    dedupe_key: str,
    xp_cost: int = 0,
    applies_to_date: date | None = None,
    note: str | None = None,
) -> bool:
    transaction = StreakFreezeTransaction(
        user_id=user_id,
        kind=kind,
        amount=amount,
        xp_cost=xp_cost,
        applies_to_date=applies_to_date,
        dedupe_key=dedupe_key,
        note=note,
        balance_after=0,
    )
    try:
        with db.begin_nested():
            db.add(transaction)
    except IntegrityError:
        return False
    transaction.balance_after = freeze_balance(db, user_id)
    db.flush()
    return True


def purchase_freeze(db: Session, user_id: uuid.UUID) -> dict:
    """Buy one freeze with XP. Enforces the per-user cap."""
    config = db.get(UserSettings, user_id) or UserSettings(user_id=user_id)
    tz = user_timezone(db, user_id)
    today = today_in(tz)

    balance = freeze_balance(db, user_id)
    if balance >= config.max_freezes:
        return {
            "purchased": False,
            "reason": f"You already hold the maximum of {config.max_freezes} freezes.",
            "balance": balance,
        }

    cost = config.freeze_cost_xp
    available = total_xp(db, user_id)
    if available < cost:
        return {
            "purchased": False,
            "reason": f"Costs {cost} XP; you have {available}.",
            "balance": balance,
            "xp_needed": cost - available,
        }

    # A unique key per purchase; the sequence number keeps repeats distinct
    # while still blocking accidental double-submits within one request.
    sequence = db.scalar(
        select(func.count(StreakFreezeTransaction.id)).where(
            StreakFreezeTransaction.user_id == user_id,
            StreakFreezeTransaction.kind == FreezeKind.PURCHASED,
        )
    )
    key = f"purchase:{sequence}"

    if not spend_xp(
        db,
        user_id,
        amount=cost,
        reason="Purchased a streak freeze",
        dedupe_key=f"freeze_purchase:{sequence}",
        activity_date=today,
    ):
        return {"purchased": False, "reason": "Not enough XP.", "balance": balance}

    _record_freeze(
        db,
        user_id,
        kind=FreezeKind.PURCHASED,
        amount=1,
        dedupe_key=key,
        xp_cost=cost,
        note="Purchased with XP",
    )
    db.commit()
    new_balance = freeze_balance(db, user_id)
    log.info("freeze purchased", user_id=str(user_id), balance=new_balance)
    return {"purchased": True, "balance": new_balance, "xp_spent": cost}


def grant_freeze(
    db: Session, user_id: uuid.UUID, *, reason: str, dedupe_key: str
) -> bool:
    """Award a freeze (milestone reward). Respects the cap."""
    config = db.get(UserSettings, user_id) or UserSettings(user_id=user_id)
    if freeze_balance(db, user_id) >= config.max_freezes:
        return False
    return _record_freeze(
        db,
        user_id,
        kind=FreezeKind.EARNED,
        amount=1,
        dedupe_key=dedupe_key,
        note=reason,
    )


# ---------------------------------------------------------------------------
# Streak computation
# ---------------------------------------------------------------------------


def _active_days(db: Session, user_id: uuid.UUID) -> list[tuple[date, bool]]:
    """Every day that counts toward a streak, oldest first."""
    rows = db.execute(
        select(ActivityDay.activity_date, ActivityDay.is_frozen)
        .where(
            ActivityDay.user_id == user_id,
            (ActivityDay.problems_solved > 0) | (ActivityDay.is_frozen.is_(True)),
        )
        .order_by(ActivityDay.activity_date)
    ).all()
    return [(row[0], bool(row[1])) for row in rows]


def compute_streak(db: Session, user_id: uuid.UUID, tz: str | None = None) -> StreakState:
    """Derive streak state from activity days. Pure read, no writes."""
    tz = tz or user_timezone(db, user_id)
    today = today_in(tz)
    days = _active_days(db, user_id)
    balance = freeze_balance(db, user_id)

    if not days:
        return StreakState(0, 0, None, balance, False)

    day_set = {d for d, _ in days}
    real_days = [d for d, frozen in days if not frozen]
    last_active = max(real_days) if real_days else None

    # Longest run across all history.
    longest = 0
    run = 0
    previous: date | None = None
    for day, _frozen in days:
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    # Current run: anchor at today if active, else yesterday (today is not yet
    # over, so an inactive today does not break anything).
    anchor = today if today in day_set else today - timedelta(days=1)
    current = 0
    if anchor in day_set:
        cursor = anchor
        while cursor in day_set:
            current += 1
            cursor -= timedelta(days=1)

    return StreakState(
        current=current,
        longest=max(longest, current),
        last_active_date=last_active,
        freezes_available=balance,
        active_today=today in day_set,
    )


def roll_over_streak(db: Session, user_id: uuid.UUID) -> StreakState:
    """Apply freezes to any missed days, then persist the streak state.

    Called on dashboard reads and by the scheduler. Idempotent: a day already
    covered by a freeze is never charged twice.
    """
    tz = user_timezone(db, user_id)
    today = today_in(tz)
    config = db.get(UserSettings, user_id) or UserSettings(user_id=user_id)

    days = _active_days(db, user_id)
    if days and config.auto_apply_freeze:
        day_set = {d for d, _ in days}
        last = max(day_set)
        # Gap days strictly between the last active day and today.
        gap_start = last + timedelta(days=1)
        gap_days = []
        cursor = gap_start
        while cursor < today:
            if cursor not in day_set:
                gap_days.append(cursor)
            cursor += timedelta(days=1)

        if gap_days and len(gap_days) <= MAX_FREEZE_LOOKBACK_DAYS:
            balance = freeze_balance(db, user_id)
            # Only bother if freezes can cover the entire gap; a partially
            # covered gap still breaks the streak, so spending would be waste.
            if 0 < len(gap_days) <= balance:
                for gap_day in gap_days:
                    applied = _record_freeze(
                        db,
                        user_id,
                        kind=FreezeKind.USED,
                        amount=1,
                        dedupe_key=f"used:{gap_day.isoformat()}",
                        applies_to_date=gap_day,
                        note="Auto-applied to protect the streak",
                    )
                    if applied:
                        frozen_day = get_or_create_activity_day(db, user_id, gap_day)
                        frozen_day.is_frozen = True
                        db.flush()
                log.info(
                    "streak freeze applied",
                    user_id=str(user_id),
                    days=[d.isoformat() for d in gap_days],
                )

    state = compute_streak(db, user_id, tz)
    _persist(db, user_id, state)
    db.commit()
    return state


def _persist(db: Session, user_id: uuid.UUID, state: StreakState) -> None:
    stats = db.get(UserStats, user_id)
    if stats is None:
        stats = UserStats(user_id=user_id)
        db.add(stats)
    stats.current_streak = state.current
    stats.longest_streak = max(state.longest, stats.longest_streak or 0)
    stats.last_active_date = state.last_active_date
    stats.available_freezes = state.freezes_available
    db.flush()


def check_streak_milestone(
    db: Session, user_id: uuid.UUID, streak: int, day: date
) -> int:
    """Award milestone XP (and a freeze) at 7/30/100/365-day marks."""
    from app.gamification.xp import award_xp, bonus_key, rules_for

    milestones = {7, 14, 30, 50, 100, 200, 365}
    if streak not in milestones:
        return 0

    rules = rules_for(db, user_id)
    amount = rules.bonus_for("streak_milestone") * max(1, streak // 7)
    granted = award_xp(
        db,
        user_id,
        amount=amount,
        kind=XPKind.BONUS,
        reason=f"{streak}-day streak",
        dedupe_key=bonus_key("streak_milestone", str(streak)),
        activity_date=day,
    )
    if granted and streak in (30, 100, 365):
        grant_freeze(
            db,
            user_id,
            reason=f"Reward for a {streak}-day streak",
            dedupe_key=f"earned:streak:{streak}",
        )
    return granted
