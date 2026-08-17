"""Deterministic recommendation engine.

This chooses *what* to solve. The AI layer only explains the choice — it never
picks problems, because a hallucinated problem id is worse than no suggestion.

Every recommendation carries structured evidence, so the reason shown to the
user is generated from real numbers rather than invented.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import SOLVED_STATUSES
from app.analytics.stats import comfortable_rating
from app.analytics.weakness import Weakness, detect_weaknesses
from app.core.logging import get_logger
from app.models.enums import ProblemStatus
from app.models.problem import Pattern, Problem, ProblemPattern, ProblemTopic, Topic
from app.models.progress import UserProblem
from app.models.recommendation import Recommendation
from app.models.sheet import Sheet, SheetProblem, SheetSection
from app.utils.timeutils import utcnow

log = get_logger(__name__)

#: How many candidates to pull per source before scoring.
CANDIDATES_PER_SOURCE = 40
#: Recommendations older than this are regenerated.
BATCH_TTL_HOURS = 12

WEIGHTS = {
    "weak_topic": 3.0,
    "weak_pattern": 2.4,
    "difficulty_fit": 2.0,
    "sheet_progression": 1.8,
    "previously_attempted": 1.5,
    "neglected_topic": 1.2,
    "collection": 0.8,
}


@dataclass
class Candidate:
    problem: Problem
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def add(self, code: str, weight: float, text: str, **evidence: Any) -> None:
        self.score += weight
        self.reason_codes.append(code)
        self.reasons.append(text)
        self.evidence.update(evidence)


def _solved_or_skipped_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(UserProblem.problem_id).where(
                UserProblem.user_id == user_id,
                UserProblem.status.in_((*SOLVED_STATUSES, ProblemStatus.SKIPPED)),
            )
        ).all()
    )


def _target_band(db: Session, user_id: uuid.UUID) -> tuple[int, int]:
    """The rating window just above the user's demonstrated comfort zone."""
    comfort = comfortable_rating(db, user_id)
    if comfort is None:
        return 800, 1100
    # One step up: enough to stretch, not enough to be demoralizing.
    return comfort, comfort + 200


def _difficulty_fit(rating: int | None, low: int, high: int) -> float:
    if rating is None:
        return 0.3
    if low <= rating <= high:
        return 1.0
    distance = min(abs(rating - low), abs(rating - high))
    return max(0.0, 1.0 - distance / 400)


def _weak_topic_candidates(
    db: Session, user_id: uuid.UUID, weaknesses: list[Weakness], excluded: set[uuid.UUID]
) -> dict[uuid.UUID, Candidate]:
    candidates: dict[uuid.UUID, Candidate] = {}
    topic_weaknesses = [w for w in weaknesses if w.kind != "pattern"][:4]
    pattern_weaknesses = [w for w in weaknesses if w.kind == "pattern"][:3]

    for weakness in topic_weaknesses:
        topic = db.scalar(select(Topic).where(Topic.slug == weakness.slug))
        if topic is None:
            continue
        descendant_ids = db.scalars(
            select(Topic.id).where(
                (Topic.path == topic.path) | (Topic.path.like(f"{topic.path}/%"))
            )
        ).all()

        problems = db.scalars(
            select(Problem)
            .join(ProblemTopic, ProblemTopic.problem_id == Problem.id)
            .where(
                ProblemTopic.topic_id.in_(descendant_ids),
                Problem.id.not_in(excluded) if excluded else True,
            )
            .limit(CANDIDATES_PER_SOURCE)
        ).all()

        for problem in problems:
            candidate = candidates.setdefault(problem.id, Candidate(problem=problem))
            candidate.add(
                "weak_topic",
                WEIGHTS["weak_topic"] * weakness.score,
                f"targets {weakness.name}, one of your weakest areas "
                f"({weakness.mastery:.0f}% mastery)",
                topic=weakness.name,
                topic_mastery=round(weakness.mastery, 1),
                topic_root_cause=weakness.root_cause_label,
                days_since_topic_practice=next(
                    (
                        e["value"]
                        for e in weakness.evidence
                        if e["metric"] == "days_since_practice"
                    ),
                    None,
                ),
            )

    for weakness in pattern_weaknesses:
        pattern = db.scalar(select(Pattern).where(Pattern.slug == weakness.slug))
        if pattern is None:
            continue
        problems = db.scalars(
            select(Problem)
            .join(ProblemPattern, ProblemPattern.problem_id == Problem.id)
            .where(
                ProblemPattern.pattern_id == pattern.id,
                Problem.id.not_in(excluded) if excluded else True,
            )
            .limit(CANDIDATES_PER_SOURCE)
        ).all()
        for problem in problems:
            candidate = candidates.setdefault(problem.id, Candidate(problem=problem))
            candidate.add(
                "weak_pattern",
                WEIGHTS["weak_pattern"] * weakness.score,
                _pattern_reason(weakness),
                pattern=weakness.name,
                pattern_mastery=round(weakness.mastery, 1),
            )

    return candidates


def _sheet_candidates(
    db: Session, user_id: uuid.UUID, excluded: set[uuid.UUID]
) -> dict[uuid.UUID, Candidate]:
    """Next unsolved problems in each sheet, in curriculum order."""
    candidates: dict[uuid.UUID, Candidate] = {}

    for sheet in db.scalars(select(Sheet)).all():
        rows = db.execute(
            select(Problem, SheetSection)
            .select_from(SheetProblem)
            .join(Problem, Problem.id == SheetProblem.problem_id)
            .outerjoin(SheetSection, SheetSection.id == SheetProblem.section_id)
            .where(
                SheetProblem.sheet_id == sheet.id,
                Problem.id.not_in(excluded) if excluded else True,
            )
            .order_by(SheetSection.sort_order, SheetProblem.order_index)
            .limit(12)
        ).all()

        for position, (problem, section) in enumerate(rows):
            candidate = candidates.setdefault(problem.id, Candidate(problem=problem))
            # Earlier in the sheet = more urgent.
            decay = max(0.3, 1.0 - position * 0.06)
            label = section.name if section else sheet.name
            candidate.add(
                "sheet_progression",
                WEIGHTS["sheet_progression"] * decay,
                f"is next up in {sheet.name} → {label}",
                sheet=sheet.name,
                sheet_section=label,
            )

    return candidates


def _attempted_candidates(
    db: Session, user_id: uuid.UUID
) -> dict[uuid.UUID, Candidate]:
    """Problems started but never finished — the cheapest wins available."""
    rows = db.execute(
        select(Problem, UserProblem)
        .join(UserProblem, UserProblem.problem_id == Problem.id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status == ProblemStatus.ATTEMPTED,
        )
        .order_by(UserProblem.last_attempted_at.desc())
        .limit(CANDIDATES_PER_SOURCE)
    ).all()

    candidates: dict[uuid.UUID, Candidate] = {}
    for problem, user_problem in rows:
        candidate = candidates.setdefault(problem.id, Candidate(problem=problem))
        candidate.add(
            "previously_attempted",
            WEIGHTS["previously_attempted"],
            f"is one you already attempted {user_problem.attempts}\u00d7 without solving",
            attempts=user_problem.attempts,
        )
    return candidates


def generate_recommendations(
    db: Session, user_id: uuid.UUID, limit: int = 6, tz: str | None = None
) -> list[dict[str, Any]]:
    """Score and rank candidate problems. Pure computation, no writes."""
    excluded = _solved_or_skipped_ids(db, user_id)
    weaknesses = detect_weaknesses(db, user_id, tz, limit=8)
    low, high = _target_band(db, user_id)

    pools = [
        _weak_topic_candidates(db, user_id, weaknesses, excluded),
        _sheet_candidates(db, user_id, excluded),
        _attempted_candidates(db, user_id),
    ]

    merged: dict[uuid.UUID, Candidate] = {}
    for pool in pools:
        for problem_id, candidate in pool.items():
            if problem_id in excluded:
                continue
            existing = merged.get(problem_id)
            if existing is None:
                merged[problem_id] = candidate
            else:
                existing.score += candidate.score
                existing.reasons.extend(candidate.reasons)
                existing.reason_codes.extend(candidate.reason_codes)
                existing.evidence.update(candidate.evidence)

    if not merged:
        return []

    for candidate in merged.values():
        fit = _difficulty_fit(candidate.problem.rating, low, high)
        candidate.score += WEIGHTS["difficulty_fit"] * fit
        candidate.evidence["target_rating_band"] = f"{low}-{high}"
        if candidate.problem.rating:
            candidate.evidence["rating"] = candidate.problem.rating
            if fit >= 0.9:
                candidate.reasons.append(f"sits in your {low}-{high} growth band")
            elif candidate.problem.rating > high:
                candidate.reasons.append(
                    f"is a stretch at {candidate.problem.rating}, above your "
                    f"{low}-{high} band"
                )

    ranked = sorted(merged.values(), key=lambda c: -c.score)[:limit]

    return [
        {
            "problem_id": str(c.problem.id),
            "problem": {
                "id": str(c.problem.id),
                "title": c.problem.title,
                "platform": c.problem.platform,
                "external_id": c.problem.external_id,
                "url": c.problem.url,
                "rating": c.problem.rating,
                "difficulty": c.problem.difficulty,
                "tags": c.problem.tags or [],
            },
            "score": round(c.score, 3),
            "reason_code": c.reason_codes[0] if c.reason_codes else "difficulty_step",
            "reason_text": _compose_reason(c),
            "reasons": c.reasons,
            "evidence": c.evidence,
            "expected_xp": _expected_xp(db, user_id, c.problem),
        }
        for c in ranked
    ]


def _pattern_reason(weakness: Weakness) -> str:
    rate = next(
        (e["value"] for e in weakness.evidence if e["metric"] == "success_rate"), None
    )
    if rate is None:
        return f"drills the {weakness.name} pattern, which is not yet solid"
    return f"drills the {weakness.name} pattern, where you succeed {rate:.0%} of the time"


def _compose_reason(candidate: Candidate) -> str:
    """Human sentence built from the candidate's real signals.

    Every clause is stored as a verb phrase so it reads correctly after "it".
    """
    if not candidate.reasons:
        return "A reasonable next step at your current level."

    unique: list[str] = []
    for reason in candidate.reasons:
        if reason not in unique:
            unique.append(reason)

    if len(unique) == 1:
        return f"Recommended because it {unique[0]}."
    return f"Recommended because it {unique[0]}, and it {unique[1]}."


def _expected_xp(db: Session, user_id: uuid.UUID, problem: Problem) -> int:
    from app.gamification.xp import rules_for

    return rules_for(db, user_id).for_problem(
        problem.platform, problem.difficulty, problem.rating
    )


def refresh_recommendations(
    db: Session, user_id: uuid.UUID, limit: int = 6, tz: str | None = None
) -> list[dict[str, Any]]:
    """Regenerate and persist a recommendation batch."""
    items = generate_recommendations(db, user_id, limit=limit, tz=tz)
    now = utcnow()
    batch_id = now.strftime("%Y%m%d%H%M%S")

    # Expire the previous batch rather than deleting it — accepted/dismissed
    # history is useful signal.
    db.query(Recommendation).filter(
        Recommendation.user_id == user_id,
        Recommendation.expires_at.is_(None),
    ).update({Recommendation.expires_at: now}, synchronize_session=False)

    for item in items:
        db.add(
            Recommendation(
                user_id=user_id,
                problem_id=uuid.UUID(item["problem_id"]),
                batch_id=batch_id,
                score=item["score"],
                reason_code=item["reason_code"],
                reason_text=item["reason_text"],
                evidence=item["evidence"],
                generated_at=now,
                expires_at=None,
            )
        )
    db.commit()
    log.info("recommendations refreshed", user_id=str(user_id), count=len(items))
    return items


def get_recommendations(
    db: Session, user_id: uuid.UUID, limit: int = 6, tz: str | None = None
) -> list[dict[str, Any]]:
    """Cached recommendations, regenerated when the batch goes stale."""
    cutoff = utcnow() - timedelta(hours=BATCH_TTL_HOURS)
    rows = db.execute(
        select(Recommendation, Problem)
        .join(Problem, Problem.id == Recommendation.problem_id)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.expires_at.is_(None),
            Recommendation.dismissed_at.is_(None),
            Recommendation.generated_at >= cutoff,
        )
        .order_by(Recommendation.score.desc())
        .limit(limit)
    ).all()

    if not rows:
        return refresh_recommendations(db, user_id, limit=limit, tz=tz)

    solved = _solved_or_skipped_ids(db, user_id)
    fresh = [(r, p) for r, p in rows if p.id not in solved]
    if len(fresh) < len(rows):
        # Something in the batch was solved — regenerate so the list stays live.
        return refresh_recommendations(db, user_id, limit=limit, tz=tz)

    return [
        {
            "id": str(rec.id),
            "problem_id": str(problem.id),
            "problem": {
                "id": str(problem.id),
                "title": problem.title,
                "platform": problem.platform,
                "external_id": problem.external_id,
                "url": problem.url,
                "rating": problem.rating,
                "difficulty": problem.difficulty,
                "tags": problem.tags or [],
            },
            "score": rec.score,
            "reason_code": rec.reason_code,
            "reason_text": rec.reason_text,
            "evidence": rec.evidence or {},
            "expected_xp": _expected_xp(db, user_id, problem),
        }
        for rec, problem in fresh
    ]


def dismiss_recommendation(
    db: Session, user_id: uuid.UUID, recommendation_id: uuid.UUID
) -> None:
    rec = db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id, Recommendation.user_id == user_id
        )
    )
    if rec is not None:
        rec.dismissed_at = utcnow()
        db.commit()


def related_problems(
    db: Session, problem_id: uuid.UUID, limit: int = 6
) -> list[dict[str, Any]]:
    """Problems sharing topics/patterns, closest in difficulty first."""
    problem = db.get(Problem, problem_id)
    if problem is None:
        return []

    topic_ids = db.scalars(
        select(ProblemTopic.topic_id).where(ProblemTopic.problem_id == problem_id)
    ).all()
    pattern_ids = db.scalars(
        select(ProblemPattern.pattern_id).where(ProblemPattern.problem_id == problem_id)
    ).all()

    if not topic_ids and not pattern_ids:
        return []

    scored = (
        select(Problem, func.count(ProblemTopic.topic_id).label("overlap"))
        .join(ProblemTopic, ProblemTopic.problem_id == Problem.id)
        .where(ProblemTopic.topic_id.in_(topic_ids), Problem.id != problem_id)
        .group_by(Problem.id)
        .order_by(func.count(ProblemTopic.topic_id).desc())
        .limit(limit * 3)
    )
    rows = db.execute(scored).all()

    def distance(other: Problem) -> int:
        if problem.rating and other.rating:
            return abs(problem.rating - other.rating)
        return 500

    ranked = sorted(rows, key=lambda row: (-row[1], distance(row[0])))[:limit]
    return [
        {
            "id": str(other.id),
            "title": other.title,
            "platform": other.platform,
            "external_id": other.external_id,
            "url": other.url,
            "rating": other.rating,
            "difficulty": other.difficulty,
            "shared_topics": int(overlap),
        }
        for other, overlap in ranked
    ]
