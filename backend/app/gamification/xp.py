"""XP ledger operations.

`award_xp` is the only way XP enters the system, and every award carries a
deterministic `dedupe_key`. The unique index on `(user_id, dedupe_key)` is what
makes double-awarding impossible — not a check-then-insert, which races.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import XPKind
from app.models.gamification import XPTransaction
from app.models.user import UserSettings
from app.gamification.rules import XPRules, level_for_xp, resolve_rules
from app.utils.timeutils import utcnow

log = get_logger(__name__)


def rules_for(db: Session, user_id: uuid.UUID) -> XPRules:
    row = db.get(UserSettings, user_id)
    return resolve_rules(row.xp_rules_override if row else None)


def award_xp(
    db: Session,
    user_id: uuid.UUID,
    *,
    amount: int,
    kind: str,
    reason: str,
    dedupe_key: str,
    activity_date: date,
    problem_id: uuid.UUID | None = None,
    commit: bool = False,
) -> int:
    """Record an XP award. Returns the XP actually granted (0 if duplicate).

    Idempotent by construction: replaying a sync, re-marking a solve, or
    toggling a status can never inflate the balance.
    """
    if amount <= 0:
        return 0

    # A duplicate award must undo only this INSERT. A bare `db.rollback()` here
    # would discard the entire in-flight transaction — including the solve that
    # triggered the award — which is how a repeated daily bonus could silently
    # erase a legitimate solve.
    try:
        with db.begin_nested():
            db.add(
                XPTransaction(
                    user_id=user_id,
                    amount=amount,
                    kind=kind,
                    reason=reason,
                    dedupe_key=dedupe_key,
                    problem_id=problem_id,
                    activity_date=activity_date,
                    awarded_at=utcnow(),
                )
            )
    except IntegrityError:
        log.debug("xp award skipped (duplicate)", dedupe_key=dedupe_key)
        return 0

    if commit:
        db.commit()
    return amount


def first_solve_key(problem_id: uuid.UUID) -> str:
    """The key that makes re-solving a problem worth zero additional XP."""
    return f"first_solve:{problem_id}"


def bonus_key(name: str, scope: str) -> str:
    return f"bonus:{name}:{scope}"


def total_xp(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == user_id
            )
        )
        or 0
    )


def xp_on_date(db: Session, user_id: uuid.UUID, day: date) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == user_id,
                XPTransaction.activity_date == day,
            )
        )
        or 0
    )


def spend_xp(
    db: Session,
    user_id: uuid.UUID,
    *,
    amount: int,
    reason: str,
    dedupe_key: str,
    activity_date: date,
) -> bool:
    """Deduct XP (e.g. buying a streak freeze).

    Returns False when the balance is insufficient; the ledger is left
    untouched so a failed purchase cannot corrupt the balance.
    """
    if amount <= 0:
        return True
    if total_xp(db, user_id) < amount:
        return False

    try:
        with db.begin_nested():
            db.add(
                XPTransaction(
                    user_id=user_id,
                    amount=-amount,
                    kind=XPKind.PURCHASE,
                    reason=reason,
                    dedupe_key=dedupe_key,
                    activity_date=activity_date,
                    awarded_at=utcnow(),
                )
            )
    except IntegrityError:
        return False
    return True


def level_info(db: Session, user_id: uuid.UUID):
    settings_row = db.get(UserSettings, user_id)
    return level_for_xp(
        total_xp(db, user_id),
        settings_row.level_config_override if settings_row else None,
    )
