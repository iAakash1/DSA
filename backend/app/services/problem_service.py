"""Canonical problem creation, metadata merging and taxonomy assignment.

Every path that can introduce a problem — sheet import, platform sync, manual
paste — funnels through `get_or_create_problem`. That is the single place where
duplicates are prevented.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import Difficulty, Platform, ProblemStatus
from app.models.problem import Pattern, Problem, ProblemPattern, ProblemTopic, Topic
from app.models.progress import UserProblem
from app.services.taxonomy import map_tags
from app.utils.normalize import (
    NormalizationError,
    ProblemRef,
    difficulty_from_rating,
    normalize_difficulty,
    parse_problem_reference,
)

log = get_logger(__name__)

#: Provenance precedence — a curated sheet mapping beats an auto-derived one.
_SOURCE_RANK = {"manual": 3, "sheet": 2, "platform": 1, "inferred": 0}


def get_problem_by_ref(db: Session, ref: ProblemRef) -> Problem | None:
    return db.scalar(
        select(Problem).where(
            Problem.platform == ref.platform, Problem.external_id == ref.external_id
        )
    )


def get_or_create_problem(
    db: Session,
    ref: ProblemRef,
    *,
    title: str | None = None,
    difficulty: str | None = None,
    rating: int | None = None,
    rating_source: str | None = None,
    tags: list[str] | None = None,
    url: str | None = None,
    acceptance_rate: float | None = None,
    solved_count: int | None = None,
    is_premium: bool | None = None,
    extra: dict[str, Any] | None = None,
    taxonomy_source: str = "platform",
    commit: bool = True,
) -> tuple[Problem, bool]:
    """Fetch or create the canonical problem for `ref`, merging new metadata.

    Merging is additive: a later import never blanks out a field it does not
    know about, and never downgrades a specific value to a vaguer one.
    """
    problem = get_problem_by_ref(db, ref)
    created = False

    if problem is None:
        problem = Problem(
            platform=ref.platform,
            external_id=ref.external_id,
            slug=ref.slug or ref.external_id,
            title=title or ref.title or ref.external_id,
            url=url or ref.url,
            difficulty=Difficulty.UNKNOWN,
            contest_id=ref.contest_id,
            problem_index=ref.index,
        )
        created = True
        try:
            with db.begin_nested():
                db.add(problem)
        except IntegrityError:
            # Lost a race with a concurrent import — adopt the winner.
            existing = get_problem_by_ref(db, ref)
            if existing is None:
                raise
            problem, created = existing, False

    if title and (created or problem.title == problem.external_id):
        problem.title = title
    if url and not problem.url:
        problem.url = url

    resolved_difficulty = normalize_difficulty(difficulty)
    if resolved_difficulty != Difficulty.UNKNOWN:
        problem.difficulty = resolved_difficulty

    if rating is not None:
        problem.rating = rating
        problem.rating_source = rating_source or problem.rating_source or "platform"
        if problem.difficulty == Difficulty.UNKNOWN:
            problem.difficulty = difficulty_from_rating(rating)

    if tags:
        merged = sorted({*(problem.tags or []), *[str(t) for t in tags]})
        problem.tags = merged
    if acceptance_rate is not None:
        problem.acceptance_rate = acceptance_rate
    if solved_count is not None:
        problem.solved_count = solved_count
    if is_premium is not None:
        problem.is_premium = is_premium
    if extra:
        problem.extra = {**(problem.extra or {}), **extra}
    if ref.contest_id is not None and problem.contest_id is None:
        problem.contest_id = ref.contest_id
        problem.problem_index = ref.index

    problem.metadata_complete = bool(
        problem.title
        and problem.title != problem.external_id
        and (problem.rating is not None or problem.difficulty != Difficulty.UNKNOWN)
    )

    if tags:
        apply_taxonomy(db, problem, tags, source=taxonomy_source)

    if commit:
        db.commit()
        db.refresh(problem)
    else:
        db.flush()
    return problem, created


def apply_taxonomy(
    db: Session,
    problem: Problem,
    tags: list[str] | None = None,
    *,
    topic_slugs: set[str] | None = None,
    pattern_slugs: set[str] | None = None,
    source: str = "platform",
) -> None:
    """Attach canonical topics/patterns to a problem.

    Existing links are kept; a link from a higher-precedence source upgrades
    the recorded provenance rather than duplicating the row.
    """
    derived_topics, derived_patterns = map_tags(tags)
    all_topics = derived_topics | (topic_slugs or set())
    all_patterns = derived_patterns | (pattern_slugs or set())
    if not all_topics and not all_patterns:
        return

    if all_topics:
        topics = db.scalars(select(Topic).where(Topic.slug.in_(all_topics))).all()
        existing = {
            link.topic_id: link
            for link in db.scalars(
                select(ProblemTopic).where(ProblemTopic.problem_id == problem.id)
            ).all()
        }
        for topic in topics:
            link = existing.get(topic.id)
            if link is None:
                db.add(
                    ProblemTopic(
                        problem_id=problem.id, topic_id=topic.id, source=source
                    )
                )
            elif _SOURCE_RANK.get(source, 0) > _SOURCE_RANK.get(link.source, 0):
                link.source = source

    if all_patterns:
        patterns = db.scalars(
            select(Pattern).where(Pattern.slug.in_(all_patterns))
        ).all()
        existing_p = {
            link.pattern_id: link
            for link in db.scalars(
                select(ProblemPattern).where(ProblemPattern.problem_id == problem.id)
            ).all()
        }
        for pattern in patterns:
            link = existing_p.get(pattern.id)
            if link is None:
                db.add(
                    ProblemPattern(
                        problem_id=problem.id, pattern_id=pattern.id, source=source
                    )
                )
            elif _SOURCE_RANK.get(source, 0) > _SOURCE_RANK.get(link.source, 0):
                link.source = source

    db.flush()


def add_problem_from_reference(
    db: Session,
    value: str,
    *,
    platform: str | None = None,
    title: str | None = None,
    difficulty: str | None = None,
    rating: int | None = None,
    tags: list[str] | None = None,
) -> tuple[Problem, bool]:
    """Add a problem from a pasted URL or identifier.

    Metadata is fetched from the platform when reachable; when it is not, the
    problem is still created from whatever the user supplied. An offline
    Codeforces must not block adding a problem.
    """
    try:
        ref = parse_problem_reference(value, platform)
    except NormalizationError as exc:
        raise ValidationError(str(exc)) from exc

    fetched: dict[str, Any] = {}
    existing = get_problem_by_ref(db, ref)
    if existing is None or not existing.metadata_complete:
        fetched = _try_fetch_metadata(ref)

    return get_or_create_problem(
        db,
        ref,
        title=title or fetched.get("title"),
        difficulty=difficulty or fetched.get("difficulty"),
        rating=rating if rating is not None else fetched.get("rating"),
        rating_source=fetched.get("rating_source"),
        tags=tags or fetched.get("tags"),
        acceptance_rate=fetched.get("acceptance_rate"),
        is_premium=fetched.get("is_premium"),
        taxonomy_source="manual" if tags else "platform",
    )


def _try_fetch_metadata(ref: ProblemRef) -> dict[str, Any]:
    """Best-effort metadata lookup. Failure is normal and never fatal."""
    if ref.platform == Platform.TAKEUFORWARD:
        # No public problem API; everything known comes from the sheet import.
        return {}
    try:
        if ref.platform == Platform.CODEFORCES:
            from app.integrations.codeforces import CodeforcesClient

            return CodeforcesClient().fetch_problem_metadata(ref) or {}
        from app.integrations.leetcode import LeetCodeClient

        return LeetCodeClient().fetch_problem_metadata(ref) or {}
    except Exception as exc:  # noqa: BLE001 - offline is an expected state
        log.info(
            "problem metadata unavailable, creating from user input",
            problem=ref.canonical_id,
            error=str(exc),
        )
        return {}


def get_user_problem(
    db: Session, user_id: uuid.UUID, problem_id: uuid.UUID, create: bool = True
) -> UserProblem | None:
    row = db.scalar(
        select(UserProblem).where(
            UserProblem.user_id == user_id, UserProblem.problem_id == problem_id
        )
    )
    if row is None and create:
        row = UserProblem(
            user_id=user_id, problem_id=problem_id, status=ProblemStatus.UNSOLVED
        )
        try:
            with db.begin_nested():
                db.add(row)
        except IntegrityError:
            row = db.scalar(
                select(UserProblem).where(
                    UserProblem.user_id == user_id,
                    UserProblem.problem_id == problem_id,
                )
            )
    return row


def require_problem(db: Session, problem_id: uuid.UUID) -> Problem:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError("Problem not found")
    return problem
