"""XP, levels, achievements, streak freezes and data import/export."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.gamification.achievements import build_metrics
from app.gamification.rules import build_level_table
from app.gamification.streaks import compute_streak, freeze_balance, purchase_freeze
from app.gamification.xp import level_info, total_xp
from app.models.gamification import (
    Achievement,
    StreakFreezeTransaction,
    UserAchievement,
    XPTransaction,
)
from app.schemas.requests import ImportRequest
from app.services.import_service import import_sheet

router = APIRouter(tags=["gamification"])


@router.get("/gamification")
def gamification(db: DbSession, user: CurrentUser) -> dict:
    level = level_info(db, user.id)
    streak = compute_streak(db, user.id, user.timezone)
    return {
        "level": level.as_dict(),
        "streak": {
            "current": streak.current,
            "longest": streak.longest,
            "active_today": streak.active_today,
            "last_active_date": streak.last_active_date.isoformat()
            if streak.last_active_date
            else None,
        },
        "freezes": {
            "available": freeze_balance(db, user.id),
        },
        "total_xp": total_xp(db, user.id),
        "levels": build_level_table(),
    }


@router.get("/gamification/xp")
def xp_history(db: DbSession, user: CurrentUser, limit: int = 50) -> dict:
    rows = db.scalars(
        select(XPTransaction)
        .where(XPTransaction.user_id == user.id)
        .order_by(XPTransaction.awarded_at.desc())
        .limit(limit)
    ).all()
    return {
        "total": total_xp(db, user.id),
        "items": [
            {
                "id": str(row.id),
                "amount": row.amount,
                "kind": row.kind,
                "reason": row.reason,
                "date": row.activity_date.isoformat(),
                "awarded_at": row.awarded_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/achievements")
def achievements(db: DbSession, user: CurrentUser) -> dict:
    unlocked = {
        row.achievement_id: row
        for row in db.scalars(
            select(UserAchievement).where(UserAchievement.user_id == user.id)
        ).all()
    }
    all_achievements = db.scalars(
        select(Achievement).order_by(Achievement.sort_order)
    ).all()
    metrics = build_metrics(db, user.id)

    return {
        "unlocked_count": len(unlocked),
        "total": len(all_achievements),
        "metrics": {
            k: v for k, v in metrics.items() if k != "topic_counts"
        },
        "items": [
            {
                "code": achievement.code,
                "name": achievement.name,
                "description": achievement.description,
                "category": achievement.category,
                "tier": achievement.tier,
                "icon": achievement.icon,
                "xp_reward": achievement.xp_reward,
                "unlocked": achievement.id in unlocked,
                "unlocked_at": unlocked[achievement.id].unlocked_at.isoformat()
                if achievement.id in unlocked
                else None,
            }
            for achievement in all_achievements
        ],
    }


@router.get("/freezes")
def freezes(db: DbSession, user: CurrentUser) -> dict:
    rows = db.scalars(
        select(StreakFreezeTransaction)
        .where(StreakFreezeTransaction.user_id == user.id)
        .order_by(StreakFreezeTransaction.created_at.desc())
        .limit(50)
    ).all()
    return {
        "available": freeze_balance(db, user.id),
        "transactions": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "amount": row.amount,
                "xp_cost": row.xp_cost,
                "applies_to_date": row.applies_to_date.isoformat()
                if row.applies_to_date
                else None,
                "note": row.note,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.post("/freezes/purchase")
def buy_freeze(db: DbSession, user: CurrentUser) -> dict:
    return purchase_freeze(db, user.id)


@router.post("/import")
def import_data(payload: ImportRequest, db: DbSession, user: CurrentUser) -> dict:
    """Import a sheet from an uploaded JSON payload."""
    report = import_sheet(db, payload.payload, enrich=payload.enrich)
    return report.as_dict()


@router.get("/export")
def export_data(db: DbSession, user: CurrentUser) -> dict:
    """Full data export. Your data is yours — this is the escape hatch."""
    from app.models.progress import (
        Mistake,
        ProblemNote,
        SolvingSession,
        Submission,
        UserProblem,
    )
    from app.models.problem import Problem

    problems = {
        p.id: p
        for p in db.scalars(
            select(Problem).join(
                UserProblem, UserProblem.problem_id == Problem.id
            ).where(UserProblem.user_id == user.id)
        ).all()
    }

    def canonical(problem_id) -> str | None:
        problem = problems.get(problem_id)
        return problem.canonical_id if problem else None

    return {
        "exported_at": __import__("datetime").datetime.now().isoformat(),
        "user": {"username": user.username, "timezone": user.timezone},
        "problems": [
            {
                "canonical_id": p.canonical_id,
                "platform": p.platform,
                "external_id": p.external_id,
                "title": p.title,
                "url": p.url,
                "rating": p.rating,
                "difficulty": p.difficulty,
                "tags": p.tags or [],
            }
            for p in problems.values()
        ],
        "progress": [
            {
                "problem": canonical(up.problem_id),
                "status": up.status,
                "attempts": up.attempts,
                "first_solved_at": up.first_solved_at.isoformat()
                if up.first_solved_at
                else None,
                "solution_source": up.best_solution_source,
                "confidence": up.confidence,
                "time_spent_seconds": up.total_time_seconds,
            }
            for up in db.scalars(
                select(UserProblem).where(UserProblem.user_id == user.id)
            ).all()
        ],
        "submissions": [
            {
                "problem": canonical(s.problem_id),
                "platform": s.platform,
                "submitted_at": s.submitted_at.isoformat(),
                "verdict": s.verdict,
                "accepted": s.is_accepted,
                "language": s.language,
            }
            for s in db.scalars(
                select(Submission).where(Submission.user_id == user.id)
            ).all()
        ],
        "sessions": [
            {
                "problem": canonical(s.problem_id),
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "time_spent_seconds": s.time_spent_seconds,
                "solution_source": s.solution_source,
                "confidence": s.confidence,
                "notes": s.notes,
            }
            for s in db.scalars(
                select(SolvingSession).where(SolvingSession.user_id == user.id)
            ).all()
        ],
        "notes": [
            {
                "problem": canonical(n.problem_id),
                "kind": n.kind,
                "content_md": n.content_md,
                "created_at": n.created_at.isoformat(),
            }
            for n in db.scalars(
                select(ProblemNote).where(ProblemNote.user_id == user.id)
            ).all()
        ],
        "mistakes": [
            {
                "problem": canonical(m.problem_id),
                "type": m.mistake_type,
                "occurred_at": m.occurred_at.isoformat(),
            }
            for m in db.scalars(
                select(Mistake).where(Mistake.user_id == user.id)
            ).all()
        ],
        "xp": [
            {
                "amount": x.amount,
                "kind": x.kind,
                "reason": x.reason,
                "date": x.activity_date.isoformat(),
            }
            for x in db.scalars(
                select(XPTransaction).where(XPTransaction.user_id == user.id)
            ).all()
        ],
    }
