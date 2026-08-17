"""Evidence-based ICPC readiness.

The one rule: a readiness number is only ever produced from activity that
actually happened. A component with too little evidence returns `None` and says
what is missing — it never returns 0, and it never returns a plausible-looking
guess. "Not enough data yet" is a correct answer; a fabricated 42% is not.

The overall score is the weighted mean of the components that *do* have
evidence, and is itself withheld until enough of them are answerable. Every
component ships the numbers it was computed from, so any figure on screen can
be traced back to rows in the database.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import SOLVED_STATUSES
from app.analytics.mastery import topic_mastery
from app.analytics.stats import comfortable_rating
from app.icpc.roadmap import NODES, PHASE_OF
from app.icpc.templates import TEMPLATES
from app.models.contest import ContestParticipation
from app.models.gamification import ActivityDay
from app.models.icpc import ICPCSettings, TemplateReview, VirtualContest
from app.models.problem import Problem
from app.models.progress import SolvingSession, UserProblem
from app.utils.timeutils import utcnow

#: Solves on one roadmap topic before its coverage is treated as real rather
#: than incidental. Matches the mastery engine's own confidence floor.
MIN_SOLVES_PER_NODE = 3

#: A team that cannot type its templates from memory loses the problems it
#: knows how to solve. Reviews older than this no longer count as recall.
TEMPLATE_RECALL_DAYS = 45

#: Rating a regional-competitive individual is generally comfortable at. Used
#: only when the user has not set their own target.
DEFAULT_TARGET_RATING = 1800

#: Components must be answerable before an overall score is shown at all.
MIN_COMPONENTS_FOR_OVERALL = 3

#: Minutes a fluent contestant takes on a problem at their comfortable rating.
#: Faster than this earns full marks; the scale is linear out to three times it,
#: because a solve that takes an hour and a half is a different skill level from
#: one that takes twenty minutes even when both are correct.
TARGET_SOLVE_MINUTES = 30

#: Timed sessions before speed is measurable rather than anecdotal.
MIN_TIMED_SESSIONS = 5

WEIGHTS: dict[str, float] = {
    "breadth": 0.25,
    "depth": 0.22,
    "implementation": 0.13,
    "speed": 0.15,
    "contest": 0.17,
    "consistency": 0.08,
}


@dataclass
class Component:
    key: str
    name: str
    #: 0..1, or None when there is not enough evidence to compute it.
    score: float | None
    #: What it was computed from — always populated, even when score is None.
    evidence: dict[str, Any] = field(default_factory=dict)
    #: Present only when `score` is None: what is missing, in plain words.
    missing: str | None = None

    @property
    def has_data(self) -> bool:
        return self.score is not None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _breadth(db: Session, user_id: uuid.UUID, tz: str | None) -> Component:
    """How much of the roadmap has real solve evidence behind it."""
    mastery = {m.slug: m for m in topic_mastery(db, user_id, tz)}

    covered: list[str] = []
    partial: list[str] = []
    untouched: list[str] = []
    for key, node in NODES.items():
        stats = mastery.get(node.topic)
        solved = stats.solved if stats else 0
        if solved >= MIN_SOLVES_PER_NODE:
            covered.append(key)
        elif solved > 0:
            partial.append(key)
        else:
            untouched.append(key)

    evidence = {
        "roadmap_nodes": len(NODES),
        "covered": len(covered),
        "partial": len(partial),
        "untouched": len(untouched),
        "min_solves_per_node": MIN_SOLVES_PER_NODE,
        "untouched_keys": sorted(untouched),
    }
    if not covered and not partial:
        return Component(
            "breadth",
            "Roadmap coverage",
            None,
            evidence,
            missing="No solves recorded against any roadmap topic yet.",
        )
    # Partial coverage counts for half — started is not finished.
    score = (len(covered) + 0.5 * len(partial)) / len(NODES)
    return Component("breadth", "Roadmap coverage", _clamp(score), evidence)


def _depth(db: Session, user_id: uuid.UUID, target: int) -> Component:
    """Comfortable rating measured against the target, not against a guess."""
    comfortable = comfortable_rating(db, user_id)
    solved_rated = db.scalar(
        select(func.count())
        .select_from(UserProblem)
        .join(Problem, Problem.id == UserProblem.problem_id)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.status.in_(SOLVED_STATUSES),
            Problem.rating.isnot(None),
        )
    ) or 0

    evidence = {
        "comfortable_rating": comfortable,
        "target_rating": target,
        "rated_problems_solved": solved_rated,
    }
    if comfortable is None:
        return Component(
            "depth",
            "Rating depth",
            None,
            evidence,
            missing=(
                "Not enough solves at a consistent rating to establish a "
                "comfortable level. Solve more rated Codeforces problems."
            ),
        )
    # 800 is the floor of the rated ladder, so progress is measured across the
    # span from there to the target rather than from zero.
    floor = 800
    span = max(target - floor, 1)
    return Component(
        "depth", "Rating depth", _clamp((comfortable - floor) / span), evidence
    )


def _implementation(db: Session, user_id: uuid.UUID) -> Component:
    """Can the templates be typed from memory, recently?"""
    cutoff = utcnow() - timedelta(days=TEMPLATE_RECALL_DAYS)
    # Aggregated in Python rather than with bool_or, which SQLite lacks — the
    # row count here is bounded by the size of the template library.
    rows = db.execute(
        select(TemplateReview.template_slug, TemplateReview.from_memory).where(
            TemplateReview.user_id == user_id, TemplateReview.reviewed_at >= cutoff
        )
    ).all()
    recalled: dict[str, bool] = {}
    for slug, memorised in rows:
        recalled[slug] = recalled.get(slug, False) or bool(memorised)

    total = len(TEMPLATES)
    reviewed = len(recalled)
    from_memory = sum(1 for memorised in recalled.values() if memorised)
    evidence = {
        "templates_in_library": total,
        "reviewed_recently": reviewed,
        "typed_from_memory": from_memory,
        "recall_window_days": TEMPLATE_RECALL_DAYS,
    }
    if reviewed == 0:
        return Component(
            "implementation",
            "Template recall",
            None,
            evidence,
            missing=(
                f"No template reviewed in the last {TEMPLATE_RECALL_DAYS} days. "
                "Review templates to measure implementation readiness."
            ),
        )
    # Reading a template is worth less than reproducing it.
    score = (from_memory + 0.4 * (reviewed - from_memory)) / total
    return Component("implementation", "Template recall", _clamp(score), evidence)


def _speed(db: Session, user_id: uuid.UUID) -> Component:
    """How long a solve takes, from timed sessions only.

    Sessions with no recorded duration are excluded rather than treated as
    instant — a platform sync knows a problem was accepted, never how long it
    took, and counting those as zero would make every synced user look fast.
    """
    rows = db.execute(
        select(
            func.count(SolvingSession.id),
            func.avg(SolvingSession.time_spent_seconds),
            func.percentile_cont(0.5).within_group(
                SolvingSession.time_spent_seconds
            )
            if db.bind and db.bind.dialect.name == "postgresql"
            else func.avg(SolvingSession.time_spent_seconds),
        ).where(
            SolvingSession.user_id == user_id,
            SolvingSession.time_spent_seconds.isnot(None),
            SolvingSession.time_spent_seconds > 0,
            SolvingSession.result == "solved",
        )
    ).one()
    timed, average, median = rows[0] or 0, rows[1], rows[2]

    evidence = {
        "timed_solves": int(timed),
        "average_minutes": round(float(average) / 60, 1) if average else None,
        "median_minutes": round(float(median) / 60, 1) if median else None,
        "target_minutes": TARGET_SOLVE_MINUTES,
        "minimum_sessions": MIN_TIMED_SESSIONS,
    }
    if timed < MIN_TIMED_SESSIONS:
        return Component(
            "speed",
            "Solving speed",
            None,
            evidence,
            missing=(
                f"Only {int(timed)} timed solve(s); speed needs at least "
                f"{MIN_TIMED_SESSIONS}. Record how long a problem took when you "
                "log it — synced solves carry no duration."
            ),
        )

    minutes = float(median) / 60
    # Full marks at or under the target, decaying linearly to zero at 3x it.
    span = TARGET_SOLVE_MINUTES * 2
    score = 1.0 - max(0.0, minutes - TARGET_SOLVE_MINUTES) / span
    return Component("speed", "Solving speed", _clamp(score), evidence)


def _contest(db: Session, user_id: uuid.UUID) -> Component:
    """Performance under a clock — real contests and self-run virtuals."""
    real = db.scalar(
        select(func.count())
        .select_from(ContestParticipation)
        .where(ContestParticipation.user_id == user_id)
    ) or 0
    solved_live = db.scalar(
        select(func.sum(ContestParticipation.problems_solved_live)).where(
            ContestParticipation.user_id == user_id
        )
    ) or 0

    virtual_rows = db.execute(
        select(
            func.count(VirtualContest.id),
            func.sum(VirtualContest.penalty_minutes),
        ).where(VirtualContest.user_id == user_id, VirtualContest.status == "finished")
    ).one()
    virtual = virtual_rows[0] or 0

    evidence = {
        "real_contests": real,
        "problems_solved_live": int(solved_live),
        "virtual_contests_finished": virtual,
    }
    total_contests = real + virtual
    if total_contests == 0:
        return Component(
            "contest",
            "Contest performance",
            None,
            evidence,
            missing=(
                "No contests recorded. Run a virtual contest or sync a real one "
                "— contest readiness cannot be inferred from practice solves."
            ),
        )
    # Two axes: having competed at all, and solving under the clock once there.
    exposure = min(total_contests / 10.0, 1.0)
    throughput = min(int(solved_live) / max(total_contests * 3.0, 1.0), 1.0)
    evidence["exposure"] = round(exposure, 3)
    evidence["throughput"] = round(throughput, 3)
    return Component(
        "contest", "Contest performance", _clamp(0.5 * exposure + 0.5 * throughput), evidence
    )


def _consistency(db: Session, user_id: uuid.UUID) -> Component:
    """Practice density over the last 8 weeks."""
    window_days = 56
    since = (utcnow() - timedelta(days=window_days)).date()
    active_days = db.scalar(
        select(func.count())
        .select_from(ActivityDay)
        .where(
            ActivityDay.user_id == user_id,
            ActivityDay.activity_date >= since,
            ActivityDay.problems_solved > 0,
        )
    ) or 0

    settings = db.get(ICPCSettings, user_id)
    weekly_target = settings.weekly_practice_days if settings else 5
    expected = max(window_days / 7.0 * weekly_target, 1.0)

    evidence = {
        "window_days": window_days,
        "active_days": active_days,
        "weekly_target_days": weekly_target,
        "expected_active_days": round(expected, 1),
    }
    if active_days == 0:
        return Component(
            "consistency",
            "Practice consistency",
            None,
            evidence,
            missing="No practice recorded in the last 8 weeks.",
        )
    return Component(
        "consistency", "Practice consistency", _clamp(active_days / expected), evidence
    )


def compute_readiness(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> dict[str, Any]:
    """Readiness, or an honest account of why it cannot be computed yet."""
    settings = db.get(ICPCSettings, user_id)
    target_is_default = not (settings and settings.target_rating)
    target = DEFAULT_TARGET_RATING if target_is_default else int(settings.target_rating)

    components = [
        _breadth(db, user_id, tz),
        _depth(db, user_id, target),
        _implementation(db, user_id),
        _speed(db, user_id),
        _contest(db, user_id),
        _consistency(db, user_id),
    ]

    answered = [c for c in components if c.has_data]
    has_sufficient_data = len(answered) >= MIN_COMPONENTS_FOR_OVERALL

    overall: float | None = None
    if has_sufficient_data:
        # Re-normalise over the components that have evidence, so a missing one
        # cannot silently drag the score toward zero.
        total_weight = sum(WEIGHTS[c.key] for c in answered)
        overall = sum(WEIGHTS[c.key] * (c.score or 0.0) for c in answered) / total_weight

    return {
        "overall": round(overall, 4) if overall is not None else None,
        "has_sufficient_data": has_sufficient_data,
        "components_answered": len(answered),
        "components_required": MIN_COMPONENTS_FOR_OVERALL,
        "target_rating": target,
        "target_rating_is_default": target_is_default,
        "blocked_reason": (
            None
            if has_sufficient_data
            else (
                f"Readiness needs at least {MIN_COMPONENTS_FOR_OVERALL} of "
                f"{len(components)} components with real evidence; "
                f"{len(answered)} available."
            )
        ),
        "components": [asdict(c) for c in components],
        "weights": WEIGHTS,
    }


def roadmap_progress(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> list[dict[str, Any]]:
    """Per-node roadmap state, joined to real solve counts."""
    mastery = {m.slug: m for m in topic_mastery(db, user_id, tz)}
    comfortable = {
        key
        for key, node in NODES.items()
        if (stats := mastery.get(node.topic)) and stats.solved >= MIN_SOLVES_PER_NODE
    }

    out: list[dict[str, Any]] = []
    for key, node in NODES.items():
        stats = mastery.get(node.topic)
        unmet = [req for req in node.requires if req not in comfortable]
        out.append(
            {
                "key": key,
                "name": node.name,
                "phase": PHASE_OF[key],
                "topic": node.topic,
                "band": list(node.band),
                "why": node.why,
                "requires": node.requires,
                "unmet_prerequisites": unmet,
                "templates": node.templates,
                "solved": stats.solved if stats else 0,
                "attempted": stats.attempted if stats else 0,
                "mastery": round(stats.mastery, 3) if stats else None,
                "confidence": stats.confidence if stats else None,
                "days_since_practice": stats.days_since_practice if stats else None,
                "state": (
                    "comfortable"
                    if key in comfortable
                    else "started"
                    if stats and stats.solved
                    else "blocked"
                    if unmet
                    else "ready"
                ),
            }
        )
    return out
