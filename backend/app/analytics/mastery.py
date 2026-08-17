"""Topic and pattern mastery.

Mastery is deliberately NOT "problems solved". Solving ten easy problems with
the editorial open is not mastery. The score combines six signals and applies a
mistake penalty, and it refuses to claim confidence on thin data.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.core import (
    SOLVED_STATUSES,
    difficulty_value,
    days_since_local,
    mastery_band,
    mean,
    recency_factor,
    safe_ratio,
)
from app.models.enums import SOLUTION_SOURCE_WEIGHT, Confidence, SolutionSource
from app.models.problem import (
    Pattern,
    Problem,
    ProblemPattern,
    ProblemTopic,
    Topic,
)
from app.models.progress import Mistake, SolvingSession, UserProblem

#: Weight of each signal in the composite score.
#:
#: Difficulty outweighs volume on purpose: forty hard problems must read as
#: stronger than a hundred easy ones. Grinding 800-rated problems saturates
#: volume, recency and diversity but leaves the difficulty term near zero, so
#: it plateaus around the middle of the scale instead of reaching "Mastered".
WEIGHTS = {
    "volume": 0.18,
    "independence": 0.20,
    "success": 0.18,
    "difficulty": 0.24,
    "recency": 0.10,
    "diversity": 0.10,
}

#: Solves needed before the volume component saturates.
VOLUME_TARGET = 12
#: Distinct patterns/subtopics needed before diversity saturates.
DIVERSITY_TARGET = 4
#: Below this, we say "not enough data" rather than pretending to know.
MIN_CONFIDENT_SOLVES = 5


@dataclass
class MasteryStats:
    slug: str
    name: str
    kind: str = "topic"
    attempted: int = 0
    solved: int = 0
    independent: int = 0
    editorial_assisted: int = 0
    #: Solves imported from a platform with no self-reported source.
    unreported: int = 0
    success_rate: float = 0.0
    avg_time_minutes: float | None = None
    avg_rating: float | None = None
    max_rating: int | None = None
    mistakes: int = 0
    distinct_children: int = 0
    days_since_practice: int | None = None
    last_practiced: datetime | None = None
    mastery: float = 0.0
    band: str = "Beginner"
    confidence: str = Confidence.INSUFFICIENT_DATA
    components: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_practiced"] = (
            self.last_practiced.isoformat() if self.last_practiced else None
        )
        data["mastery"] = round(self.mastery, 1)
        data["success_rate"] = round(self.success_rate, 3)
        if self.avg_time_minutes is not None:
            data["avg_time_minutes"] = round(self.avg_time_minutes, 1)
        if self.avg_rating is not None:
            data["avg_rating"] = round(self.avg_rating)
        data["components"] = {k: round(v, 3) for k, v in self.components.items()}
        return data


def _score(stats: MasteryStats, difficulty: float) -> None:
    volume = min(1.0, stats.solved / VOLUME_TARGET)

    independence = 0.0
    if stats.solved:
        # Whatever is left after the three tracked buckets was hint-assisted.
        hinted = max(
            0, stats.solved - stats.independent - stats.editorial_assisted - stats.unreported
        )
        weighted = (
            stats.independent * SOLUTION_SOURCE_WEIGHT[SolutionSource.INDEPENDENT]
            + stats.editorial_assisted * SOLUTION_SOURCE_WEIGHT[SolutionSource.EDITORIAL]
            + stats.unreported * SOLUTION_SOURCE_WEIGHT[SolutionSource.UNKNOWN]
            + hinted * SOLUTION_SOURCE_WEIGHT[SolutionSource.HINT]
        )
        independence = min(1.0, weighted / stats.solved)

    success = stats.success_rate
    difficulty = max(0.0, min(1.0, difficulty))
    recency = recency_factor(stats.days_since_practice)
    diversity = min(1.0, stats.distinct_children / DIVERSITY_TARGET)

    components = {
        "volume": volume,
        "independence": independence,
        "success": success,
        "difficulty": difficulty,
        "recency": recency,
        "diversity": diversity,
    }
    raw = sum(WEIGHTS[key] * value for key, value in components.items())

    # Repeated mistakes in a topic are direct evidence against mastery.
    mistake_rate = safe_ratio(stats.mistakes, max(1, stats.solved))
    penalty = min(0.25, mistake_rate * 0.4)

    stats.components = components
    stats.mastery = max(0.0, min(100.0, raw * (1 - penalty) * 100))
    stats.band = mastery_band(stats.mastery)

    if stats.solved < MIN_CONFIDENT_SOLVES:
        stats.confidence = Confidence.INSUFFICIENT_DATA
    elif stats.solved < 10 or stats.attempted < 6:
        stats.confidence = Confidence.LOW
    elif stats.solved < 25:
        stats.confidence = Confidence.MEDIUM
    else:
        stats.confidence = Confidence.HIGH


def _finalize(stats: MasteryStats, difficulty_values: list[float]) -> MasteryStats:
    _score(stats, mean(difficulty_values) or 0.0)
    return stats


def topic_mastery(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> list[MasteryStats]:
    """Mastery per topic, rolled up through the hierarchy.

    A Dijkstra solve counts toward Dijkstra, Shortest Path *and* Graphs — which
    is what makes the parent-level numbers meaningful.
    """
    topics = {t.id: t for t in db.scalars(select(Topic)).all()}
    by_slug = {t.slug: t for t in topics.values()}

    rows = db.execute(
        select(
            Topic.id,
            UserProblem.problem_id,
            UserProblem.status,
            UserProblem.best_solution_source,
            UserProblem.first_solved_at,
            UserProblem.last_solved_at,
            UserProblem.last_attempted_at,
            Problem.rating,
            Problem.difficulty,
        )
        .select_from(UserProblem)
        .join(ProblemTopic, ProblemTopic.problem_id == UserProblem.problem_id)
        .join(Topic, Topic.id == ProblemTopic.topic_id)
        .join(Problem, Problem.id == UserProblem.problem_id)
        .where(UserProblem.user_id == user_id)
    ).all()

    mistake_rows = db.execute(
        select(Topic.id, func.count(Mistake.id))
        .select_from(Mistake)
        .join(ProblemTopic, ProblemTopic.problem_id == Mistake.problem_id)
        .join(Topic, Topic.id == ProblemTopic.topic_id)
        .where(Mistake.user_id == user_id)
        .group_by(Topic.id)
    ).all()
    mistakes_by_topic = {tid: int(count) for tid, count in mistake_rows}

    time_rows = db.execute(
        select(Topic.id, SolvingSession.time_spent_seconds)
        .select_from(SolvingSession)
        .join(ProblemTopic, ProblemTopic.problem_id == SolvingSession.problem_id)
        .join(Topic, Topic.id == ProblemTopic.topic_id)
        .where(
            SolvingSession.user_id == user_id,
            SolvingSession.result == "solved",
            SolvingSession.time_spent_seconds.is_not(None),
        )
    ).all()

    # Accumulate against every ancestor via the materialized path.
    acc: dict[str, dict[str, Any]] = {}

    def bucket(slug: str) -> dict[str, Any]:
        if slug not in acc:
            acc[slug] = {
                "problems": set(),
                "solved": set(),
                "independent": set(),
                "editorial": set(),
                "unreported": set(),
                "difficulty": [],
                "ratings": [],
                "children": set(),
                "last": None,
                "mistakes": 0,
                "times": [],
            }
        return acc[slug]

    for (
        topic_id,
        problem_id,
        status,
        source,
        first_solved_at,
        last_solved_at,
        last_attempted_at,
        rating,
        difficulty,
    ) in rows:
        topic = topics.get(topic_id)
        if topic is None:
            continue
        ancestors = [a for a in (topic.path or topic.slug).split("/") if a]
        is_solved = status in SOLVED_STATUSES and first_solved_at is not None
        touched_at = last_solved_at or last_attempted_at

        for ancestor in ancestors:
            b = bucket(ancestor)
            b["problems"].add(problem_id)
            if ancestor != topic.slug:
                b["children"].add(topic.slug)
            if is_solved:
                b["solved"].add(problem_id)
                b["difficulty"].append(difficulty_value(difficulty, rating))
                if rating:
                    b["ratings"].append(float(rating))
                if source == SolutionSource.INDEPENDENT:
                    b["independent"].add(problem_id)
                elif source in (SolutionSource.EDITORIAL, SolutionSource.DISCUSSION, SolutionSource.COPIED):
                    b["editorial"].add(problem_id)
                elif source in (None, SolutionSource.UNKNOWN):
                    b["unreported"].add(problem_id)
            if touched_at and (b["last"] is None or touched_at > b["last"]):
                b["last"] = touched_at

    for topic_id, count in mistakes_by_topic.items():
        topic = topics.get(topic_id)
        if topic is None:
            continue
        for ancestor in (topic.path or topic.slug).split("/"):
            if ancestor:
                bucket(ancestor)["mistakes"] += count

    for topic_id, seconds in time_rows:
        topic = topics.get(topic_id)
        if topic is None or not seconds:
            continue
        for ancestor in (topic.path or topic.slug).split("/"):
            if ancestor:
                bucket(ancestor)["times"].append(float(seconds) / 60.0)

    results: list[MasteryStats] = []
    for slug, data in acc.items():
        topic = by_slug.get(slug)
        if topic is None:
            continue
        solved = len(data["solved"])
        attempted = len(data["problems"])
        stats = MasteryStats(
            slug=slug,
            name=topic.name,
            kind=topic.kind,
            attempted=attempted,
            solved=solved,
            independent=len(data["independent"]),
            editorial_assisted=len(data["editorial"]),
            unreported=len(data["unreported"]),
            success_rate=safe_ratio(solved, attempted),
            avg_time_minutes=mean(data["times"]),
            avg_rating=mean(data["ratings"]),
            max_rating=int(max(data["ratings"])) if data["ratings"] else None,
            mistakes=data["mistakes"],
            distinct_children=len(data["children"]) or (1 if solved else 0),
            days_since_practice=days_since_local(data["last"], tz),
            last_practiced=data["last"],
        )
        results.append(_finalize(stats, data["difficulty"]))

    results.sort(key=lambda s: (-s.solved, s.name))
    return results


def pattern_mastery(
    db: Session, user_id: uuid.UUID, tz: str | None = None
) -> list[MasteryStats]:
    """Mastery per solving pattern. Flat — patterns have no hierarchy."""
    patterns = {p.id: p for p in db.scalars(select(Pattern)).all()}

    rows = db.execute(
        select(
            Pattern.id,
            UserProblem.problem_id,
            UserProblem.status,
            UserProblem.best_solution_source,
            UserProblem.first_solved_at,
            UserProblem.last_solved_at,
            UserProblem.last_attempted_at,
            Problem.rating,
            Problem.difficulty,
        )
        .select_from(UserProblem)
        .join(ProblemPattern, ProblemPattern.problem_id == UserProblem.problem_id)
        .join(Pattern, Pattern.id == ProblemPattern.pattern_id)
        .join(Problem, Problem.id == UserProblem.problem_id)
        .where(UserProblem.user_id == user_id)
    ).all()

    mistake_rows = db.execute(
        select(Pattern.id, func.count(Mistake.id))
        .select_from(Mistake)
        .join(ProblemPattern, ProblemPattern.problem_id == Mistake.problem_id)
        .join(Pattern, Pattern.id == ProblemPattern.pattern_id)
        .where(Mistake.user_id == user_id)
        .group_by(Pattern.id)
    ).all()
    mistakes_by_pattern = {pid: int(c) for pid, c in mistake_rows}

    time_rows = db.execute(
        select(Pattern.id, SolvingSession.time_spent_seconds)
        .select_from(SolvingSession)
        .join(ProblemPattern, ProblemPattern.problem_id == SolvingSession.problem_id)
        .join(Pattern, Pattern.id == ProblemPattern.pattern_id)
        .where(
            SolvingSession.user_id == user_id,
            SolvingSession.result == "solved",
            SolvingSession.time_spent_seconds.is_not(None),
        )
    ).all()
    times: dict[uuid.UUID, list[float]] = {}
    for pattern_id, seconds in time_rows:
        if seconds:
            times.setdefault(pattern_id, []).append(float(seconds) / 60.0)

    acc: dict[uuid.UUID, dict[str, Any]] = {}
    for (
        pattern_id,
        problem_id,
        status,
        source,
        first_solved_at,
        last_solved_at,
        last_attempted_at,
        rating,
        difficulty,
    ) in rows:
        data = acc.setdefault(
            pattern_id,
            {
                "problems": set(),
                "solved": set(),
                "independent": set(),
                "editorial": set(),
                "unreported": set(),
                "difficulty": [],
                "ratings": [],
                "last": None,
            },
        )
        data["problems"].add(problem_id)
        touched_at = last_solved_at or last_attempted_at
        if status in SOLVED_STATUSES and first_solved_at is not None:
            data["solved"].add(problem_id)
            data["difficulty"].append(difficulty_value(difficulty, rating))
            if rating:
                data["ratings"].append(float(rating))
            if source == SolutionSource.INDEPENDENT:
                data["independent"].add(problem_id)
            elif source in (SolutionSource.EDITORIAL, SolutionSource.DISCUSSION, SolutionSource.COPIED):
                data["editorial"].add(problem_id)
            elif source in (None, SolutionSource.UNKNOWN):
                data["unreported"].add(problem_id)
        if touched_at and (data["last"] is None or touched_at > data["last"]):
            data["last"] = touched_at

    results: list[MasteryStats] = []
    for pattern_id, data in acc.items():
        pattern = patterns.get(pattern_id)
        if pattern is None:
            continue
        solved = len(data["solved"])
        attempted = len(data["problems"])
        stats = MasteryStats(
            slug=pattern.slug,
            name=pattern.name,
            kind="pattern",
            attempted=attempted,
            solved=solved,
            independent=len(data["independent"]),
            editorial_assisted=len(data["editorial"]),
            unreported=len(data["unreported"]),
            success_rate=safe_ratio(solved, attempted),
            avg_time_minutes=mean(times.get(pattern_id, [])),
            avg_rating=mean(data["ratings"]),
            max_rating=int(max(data["ratings"])) if data["ratings"] else None,
            mistakes=mistakes_by_pattern.get(pattern_id, 0),
            distinct_children=min(DIVERSITY_TARGET, solved),
            days_since_practice=days_since_local(data["last"], tz),
            last_practiced=data["last"],
        )
        results.append(_finalize(stats, data["difficulty"]))

    results.sort(key=lambda s: (-s.solved, s.name))
    return results


def untouched_topics(db: Session, user_id: uuid.UUID) -> list[dict[str, str]]:
    """Top-level topics with zero recorded activity."""
    touched = set(
        db.scalars(
            select(Topic.path)
            .join(ProblemTopic, ProblemTopic.topic_id == Topic.id)
            .join(UserProblem, UserProblem.problem_id == ProblemTopic.problem_id)
            .where(UserProblem.user_id == user_id)
        ).all()
    )
    touched_slugs = {part for path in touched for part in (path or "").split("/") if part}

    return [
        {"slug": topic.slug, "name": topic.name}
        for topic in db.scalars(
            select(Topic).where(Topic.depth == 0).order_by(Topic.sort_order)
        ).all()
        if topic.slug not in touched_slugs
    ]
