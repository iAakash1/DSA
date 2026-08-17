"""Editorial and video resources for a problem."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_TRUSTED_CHANNELS, settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations.base import IntegrationError
from app.integrations.youtube import YouTubeClient, score_candidate
from app.models.editorial import Resource, TrustedChannel
from app.models.enums import Platform, ResourceKind
from app.models.problem import Problem
from app.utils.normalize import is_safe_external_url

log = get_logger(__name__)

_YOUTUBE_HOSTS = {"youtube.com", "youtu.be"}


def trusted_channels(db: Session, user_id: uuid.UUID) -> list[TrustedChannel]:
    """The user's channels, falling back to the built-in defaults."""
    rows = list(
        db.scalars(
            select(TrustedChannel).where(
                (TrustedChannel.user_id == user_id) | (TrustedChannel.user_id.is_(None)),
                TrustedChannel.enabled.is_(True),
            )
        ).all()
    )
    if rows:
        return rows

    seeded = [
        TrustedChannel(user_id=None, channel_id=channel_id, name=name)
        for name, channel_id in DEFAULT_TRUSTED_CHANNELS.items()
    ]
    db.add_all(seeded)
    db.commit()
    return seeded


def add_trusted_channel(
    db: Session, user_id: uuid.UUID, channel_id: str, name: str, weight: float = 1.0
) -> TrustedChannel:
    existing = db.scalar(
        select(TrustedChannel).where(
            TrustedChannel.user_id == user_id, TrustedChannel.channel_id == channel_id
        )
    )
    if existing is not None:
        existing.name = name
        existing.weight = weight
        existing.enabled = True
    else:
        existing = TrustedChannel(
            user_id=user_id, channel_id=channel_id, name=name, weight=weight
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def get_resources(
    db: Session, user_id: uuid.UUID, problem_id: uuid.UUID, refresh: bool = False
) -> dict[str, Any]:
    """Cached resources for a problem, searching YouTube only when needed."""
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError("Problem not found")

    cached = list(
        db.scalars(
            select(Resource)
            .where(Resource.problem_id == problem_id)
            .order_by(Resource.is_selected.desc(), Resource.score.desc())
        ).all()
    )

    if cached and not refresh:
        return _serialize(problem, cached, source="cache")

    if not settings.youtube_configured:
        return {
            **_serialize(problem, cached, source="cache"),
            "available": False,
            "message": (
                "Video search is unavailable because no YouTube API key is "
                "configured. You can still add an editorial link manually."
            ),
        }

    try:
        discovered = _search(db, user_id, problem)
    except IntegrationError as exc:
        log.warning("youtube search failed", problem=problem.canonical_id, error=exc.message)
        return {
            **_serialize(problem, cached, source="cache"),
            "available": False,
            "message": f"YouTube search is temporarily unavailable ({exc.message}).",
        }

    return _serialize(problem, discovered, source="youtube")


def _search(db: Session, user_id: uuid.UUID, problem: Problem) -> list[Resource]:
    client = YouTubeClient()
    channels = trusted_channels(db, user_id)

    # Query text that actually identifies the problem on both platforms.
    if problem.platform == Platform.CODEFORCES:
        query = f"Codeforces {problem.external_id} {problem.title}"
    else:
        query = f"{problem.title} LeetCode"

    candidates = []
    for channel in channels:
        try:
            found = client.search_channel(channel.channel_id, query, limit=4)
        except IntegrationError as exc:
            log.info("channel search failed", channel=channel.name, error=exc.message)
            continue
        for candidate in found:
            candidate.breakdown = {"channel_weight": channel.weight}
            candidates.append((candidate, channel.weight))

    if not candidates:
        return []

    client.hydrate_durations([c for c, _ in candidates])

    scored: list[Resource] = []
    for candidate, weight in candidates:
        score, breakdown = score_candidate(
            candidate,
            problem_title=problem.title,
            external_id=problem.external_id,
            platform=problem.platform,
            channel_weight=weight,
        )
        candidate.score = score

        existing = db.scalar(
            select(Resource).where(
                Resource.problem_id == problem.id, Resource.url == candidate.url
            )
        )
        if existing is None:
            existing = Resource(
                problem_id=problem.id,
                kind=ResourceKind.VIDEO,
                title=candidate.title,
                url=candidate.url,
                provider="youtube",
                external_id=candidate.external_id,
                channel_id=candidate.channel_id,
                channel_title=candidate.channel_title,
                duration_seconds=candidate.duration_seconds,
                published_at=candidate.published_at,
                thumbnail_url=candidate.thumbnail_url,
            )
            db.add(existing)
        existing.score = score
        existing.score_breakdown = breakdown
        scored.append(existing)

    db.flush()
    scored.sort(key=lambda r: -r.score)

    # Auto-select the best candidate, but only when it clearly matches.
    if scored and scored[0].score >= 4.0:
        for resource in scored:
            resource.is_selected = False
        scored[0].is_selected = True

    db.commit()
    return scored


def add_manual_resource(
    db: Session,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    url: str,
    title: str,
    kind: str = ResourceKind.VIDEO,
) -> Resource:
    """Manual override — always wins over anything discovered."""
    if not is_safe_external_url(url):
        raise ValidationError("That does not look like a valid http(s) URL")

    resource = db.scalar(
        select(Resource).where(Resource.problem_id == problem_id, Resource.url == url)
    )
    if resource is None:
        resource = Resource(
            problem_id=problem_id,
            user_id=user_id,
            kind=kind,
            title=title,
            url=url,
            provider="youtube" if any(h in url for h in _YOUTUBE_HOSTS) else "web",
        )
        db.add(resource)

    for other in db.scalars(
        select(Resource).where(Resource.problem_id == problem_id)
    ).all():
        other.is_selected = False

    resource.is_manual = True
    resource.is_selected = True
    resource.score = 99.0
    db.commit()
    db.refresh(resource)
    return resource


def select_resource(
    db: Session, user_id: uuid.UUID, problem_id: uuid.UUID, resource_id: uuid.UUID
) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None or resource.problem_id != problem_id:
        raise NotFoundError("Resource not found")
    for other in db.scalars(
        select(Resource).where(Resource.problem_id == problem_id)
    ).all():
        other.is_selected = False
    resource.is_selected = True
    db.commit()
    db.refresh(resource)
    return resource


def _serialize(
    problem: Problem, resources: list[Resource], source: str
) -> dict[str, Any]:
    return {
        "problem_id": str(problem.id),
        "problem_title": problem.title,
        "available": True,
        "source": source,
        "selected": next(
            (
                {
                    "id": str(r.id),
                    "title": r.title,
                    "url": r.url,
                    "external_id": r.external_id,
                    "channel_title": r.channel_title,
                    "duration_seconds": r.duration_seconds,
                }
                for r in resources
                if r.is_selected
            ),
            None,
        ),
        "candidates": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "title": r.title,
                "url": r.url,
                "external_id": r.external_id,
                "channel_title": r.channel_title,
                "duration_seconds": r.duration_seconds,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "thumbnail_url": r.thumbnail_url,
                "score": r.score,
                "score_breakdown": r.score_breakdown,
                "is_selected": r.is_selected,
                "is_manual": r.is_manual,
            }
            for r in resources
        ],
    }
