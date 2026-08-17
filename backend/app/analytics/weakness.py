"""Weakness detection.

A topic is weak when *several independent signals* agree, and the output always
carries the evidence. Crucially, it distinguishes two very different problems:

    "you have not practiced this enough"      -> exposure
    "you practice this and still struggle"    -> comprehension / execution

Those need opposite interventions, so conflating them makes the advice useless.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import mean, median, safe_ratio
from app.analytics.mastery import MasteryStats, pattern_mastery, topic_mastery
from app.models.enums import (
    CONCEPTUAL_MISTAKES,
    IMPLEMENTATION_MISTAKES,
    Confidence,
)
from app.models.problem import ProblemTopic, Topic
from app.models.progress import Mistake

#: A topic needs this many attempts before we will judge it at all.
MIN_ATTEMPTS_TO_JUDGE = 3
#: Success rate this far below the personal baseline is a signal.
SUCCESS_GAP = 0.15
#: Solve time this multiple of the personal median is a signal.
TIME_MULTIPLIER = 1.4
#: Days without practice before staleness counts as a signal.
STALE_DAYS = 14
#: Share of solves that needed an editorial before dependence is a signal.
EDITORIAL_DEPENDENCE = 0.35


@dataclass
class Weakness:
    slug: str
    name: str
    kind: str
    severity: str
    mastery: float
    confidence: str
    root_cause: str
    root_cause_label: str
    recommended_action: str
    recommended_difficulty: str | None
    signals: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mastery"] = round(self.mastery, 1)
        data["score"] = round(self.score, 3)
        return data


_ROOT_CAUSE_LABELS = {
    "insufficient_exposure": "Not enough practice yet",
    "concept": "Concept / approach selection",
    "implementation": "Implementation reliability",
    "speed": "Speed, not correctness",
    "retention": "Retention — you knew this, it faded",
    "dependence": "Over-reliance on editorials",
}


def _baselines(db: Session, user_id: uuid.UUID, topics: list[MasteryStats]) -> dict[str, float]:
    overall_success = mean([t.success_rate for t in topics if t.attempted >= 2]) or 0.0
    overall_time = median(
        [t.avg_time_minutes for t in topics if t.avg_time_minutes is not None]
    )
    overall_rating = mean([t.avg_rating for t in topics if t.avg_rating is not None])
    return {
        "success_rate": overall_success,
        "median_time_minutes": overall_time or 0.0,
        "average_rating": overall_rating or 0.0,
    }


def _mistake_profile(db: Session, user_id: uuid.UUID) -> dict[str, dict[str, int]]:
    """Implementation vs conceptual mistake counts per topic slug."""
    rows = db.execute(
        select(Topic.path, Mistake.mistake_type, func.count(Mistake.id))
        .select_from(Mistake)
        .join(ProblemTopic, ProblemTopic.problem_id == Mistake.problem_id)
        .join(Topic, Topic.id == ProblemTopic.topic_id)
        .where(Mistake.user_id == user_id)
        .group_by(Topic.path, Mistake.mistake_type)
    ).all()

    profile: dict[str, dict[str, int]] = {}
    for path, mistake_type, count in rows:
        for slug in (path or "").split("/"):
            if not slug:
                continue
            entry = profile.setdefault(slug, {"implementation": 0, "conceptual": 0})
            if mistake_type in IMPLEMENTATION_MISTAKES:
                entry["implementation"] += int(count)
            elif mistake_type in CONCEPTUAL_MISTAKES:
                entry["conceptual"] += int(count)
    return profile


def _analyze(
    stats: MasteryStats,
    baselines: dict[str, float],
    mistakes: dict[str, int] | None,
) -> Weakness | None:
    if stats.attempted < MIN_ATTEMPTS_TO_JUDGE:
        return None

    signals: list[str] = []
    evidence: list[dict[str, Any]] = []
    score = 0.0

    baseline_success = baselines["success_rate"]
    if baseline_success and stats.success_rate < baseline_success - SUCCESS_GAP:
        signals.append("low_success_rate")
        score += 0.30
        evidence.append(
            {
                "metric": "success_rate",
                "value": round(stats.success_rate, 3),
                "comparison": round(baseline_success, 3),
                "description": (
                    f"{stats.success_rate:.0%} success rate versus your "
                    f"{baseline_success:.0%} baseline"
                ),
            }
        )

    baseline_time = baselines["median_time_minutes"]
    if (
        baseline_time
        and stats.avg_time_minutes
        and stats.avg_time_minutes > baseline_time * TIME_MULTIPLIER
    ):
        signals.append("slow_solve_time")
        score += 0.18
        evidence.append(
            {
                "metric": "avg_time_minutes",
                "value": round(stats.avg_time_minutes, 1),
                "comparison": round(baseline_time, 1),
                "description": (
                    f"{stats.avg_time_minutes:.0f} min average versus your "
                    f"{baseline_time:.0f} min median"
                ),
            }
        )

    if stats.days_since_practice is not None and stats.days_since_practice > STALE_DAYS:
        signals.append("not_practiced_recently")
        score += 0.15
        evidence.append(
            {
                "metric": "days_since_practice",
                "value": stats.days_since_practice,
                "comparison": STALE_DAYS,
                "description": f"Last practiced {stats.days_since_practice} days ago",
            }
        )

    editorial_share = safe_ratio(stats.editorial_assisted, max(1, stats.solved))
    if stats.solved >= 3 and editorial_share > EDITORIAL_DEPENDENCE:
        signals.append("editorial_dependence")
        score += 0.20
        evidence.append(
            {
                "metric": "editorial_share",
                "value": round(editorial_share, 3),
                "comparison": EDITORIAL_DEPENDENCE,
                "description": (
                    f"{stats.editorial_assisted} of {stats.solved} solves needed an editorial"
                ),
            }
        )

    mistake_rate = safe_ratio(stats.mistakes, max(1, stats.solved))
    if stats.mistakes >= 3 and mistake_rate > 0.4:
        signals.append("repeated_mistakes")
        score += 0.22
        evidence.append(
            {
                "metric": "mistakes",
                "value": stats.mistakes,
                "comparison": stats.solved,
                "description": f"{stats.mistakes} recorded mistakes across {stats.solved} solves",
            }
        )

    baseline_rating = baselines["average_rating"]
    if (
        baseline_rating
        and stats.max_rating
        and stats.max_rating < baseline_rating - 150
        and stats.solved >= 4
    ):
        signals.append("low_difficulty_ceiling")
        score += 0.12
        evidence.append(
            {
                "metric": "max_rating",
                "value": stats.max_rating,
                "comparison": round(baseline_rating),
                "description": (
                    f"Highest solved here is {stats.max_rating}, below your "
                    f"{baseline_rating:.0f} average"
                ),
            }
        )

    if stats.solved < 5 and stats.attempted >= MIN_ATTEMPTS_TO_JUDGE:
        signals.append("thin_exposure")
        score += 0.15
        evidence.append(
            {
                "metric": "solved",
                "value": stats.solved,
                "comparison": 5,
                "description": f"Only {stats.solved} solved in this area",
            }
        )

    if not signals:
        return None

    root_cause = _classify(stats, signals, mistakes)
    severity = "high" if score >= 0.55 else "medium" if score >= 0.3 else "low"

    return Weakness(
        slug=stats.slug,
        name=stats.name,
        kind=stats.kind,
        severity=severity,
        mastery=stats.mastery,
        confidence=stats.confidence,
        root_cause=root_cause,
        root_cause_label=_ROOT_CAUSE_LABELS[root_cause],
        recommended_action=_action_for(root_cause, stats),
        recommended_difficulty=_difficulty_band(stats),
        signals=signals,
        evidence=evidence,
        score=score,
    )


def _classify(
    stats: MasteryStats, signals: list[str], mistakes: dict[str, int] | None
) -> str:
    """Separate 'never learned it' from 'learned it and still fail'."""
    if stats.solved < 5:
        return "insufficient_exposure"

    if mistakes:
        implementation = mistakes.get("implementation", 0)
        conceptual = mistakes.get("conceptual", 0)
        if implementation and implementation > conceptual * 1.5:
            return "implementation"
        if conceptual and conceptual > implementation * 1.5:
            return "concept"

    if "editorial_dependence" in signals:
        return "dependence"
    if "low_success_rate" in signals:
        return "concept"
    if "slow_solve_time" in signals and "low_success_rate" not in signals:
        return "speed"
    if signals == ["not_practiced_recently"] or "not_practiced_recently" in signals:
        return "retention"
    return "concept"


def _action_for(root_cause: str, stats: MasteryStats) -> str:
    band = _difficulty_band(stats) or "your current level"
    actions = {
        "insufficient_exposure": (
            f"Solve 5-8 more {stats.name} problems at {band} before judging this area."
        ),
        "concept": (
            f"Work through {stats.name} fundamentals again, then solve 3 problems at "
            f"{band} writing the approach down before coding."
        ),
        "implementation": (
            f"Your approach selection is fine — spend 5 minutes on edge cases before "
            f"submitting. Do 5 implementation-heavy {stats.name} problems at {band}."
        ),
        "speed": (
            f"Correctness is there; practise {stats.name} under a timer at {band} to "
            "build recognition speed."
        ),
        "retention": (
            f"Revisit 2-3 {stats.name} problems you have already solved, then attempt "
            f"one new problem at {band}."
        ),
        "dependence": (
            f"Attempt {stats.name} problems at {band} for a full 40 minutes before "
            "opening any editorial."
        ),
    }
    return actions[root_cause]


def _difficulty_band(stats: MasteryStats) -> str | None:
    if stats.avg_rating:
        base = int(stats.avg_rating // 100 * 100)
        return f"{base}-{base + 200}"
    if stats.kind == "pattern" or stats.solved:
        return "1100-1300"
    return None


def detect_weaknesses(
    db: Session,
    user_id: uuid.UUID,
    tz: str | None = None,
    limit: int = 8,
    include_patterns: bool = True,
) -> list[Weakness]:
    """Rank weak areas across topics and patterns, strongest signal first."""
    topics = topic_mastery(db, user_id, tz)
    if not topics:
        return []

    baselines = _baselines(db, user_id, topics)
    mistake_profile = _mistake_profile(db, user_id)

    findings: list[Weakness] = []
    for stats in topics:
        # Leaf/technique nodes give more actionable advice than umbrella topics,
        # but keep top-level topics too so the picture stays legible.
        weakness = _analyze(stats, baselines, mistake_profile.get(stats.slug))
        if weakness:
            findings.append(weakness)

    if include_patterns:
        patterns = pattern_mastery(db, user_id, tz)
        for stats in patterns:
            weakness = _analyze(stats, baselines, None)
            if weakness:
                findings.append(weakness)

    findings.sort(key=lambda w: (-w.score, w.mastery))

    # Several patterns share a name with their parent topic ("Game Theory" is
    # both). Reporting both is noise — keep the strongest signal per name.
    deduped: list[Weakness] = []
    seen: set[str] = set()
    for finding in findings:
        key = finding.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)

    return deduped[:limit]


def weakness_summary(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> dict[str, Any]:
    findings = detect_weaknesses(db, user_id, tz)
    topics = topic_mastery(db, user_id, tz)
    confident = [t for t in topics if t.confidence != Confidence.INSUFFICIENT_DATA]

    return {
        "weaknesses": [w.as_dict() for w in findings],
        "weakest_topic": findings[0].name if findings else None,
        "strongest_topics": [
            {"name": t.name, "slug": t.slug, "mastery": round(t.mastery, 1)}
            for t in sorted(confident, key=lambda t: -t.mastery)[:5]
        ],
        "has_enough_data": len(confident) >= 3,
        "analyzed_topics": len(topics),
    }
