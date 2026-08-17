"""YouTube Data API v3 — trusted-channel editorial search.

Never a blind scrape and never "most viewed wins". Candidates are restricted to
channels the user trusts, then scored on how well they actually match the
problem. The user can always override the choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.base import BaseClient, NotAvailable

log = get_logger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"

#: Editorials are rarely under 2 minutes or over 2 hours.
MIN_SENSIBLE_SECONDS = 120
MAX_SENSIBLE_SECONDS = 7200

_DURATION = re.compile(
    r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


@dataclass
class VideoCandidate:
    external_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: datetime | None
    thumbnail_url: str | None
    duration_seconds: int | None = None
    score: float = 0.0
    breakdown: dict[str, float] | None = None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.external_id}"


def parse_duration(value: str | None) -> int | None:
    if not value:
        return None
    match = _DURATION.fullmatch(value)
    if not match:
        return None
    parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


class YouTubeClient(BaseClient):
    service_name = "YouTube"
    min_interval = 0.2
    default_cache_ttl = 3600.0 * 24

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_key = settings.youtube_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search_channel(
        self, channel_id: str, query: str, limit: int = 5
    ) -> list[VideoCandidate]:
        """Search within a single trusted channel."""
        if not self.configured:
            raise NotAvailable(self.service_name, "No YouTube API key configured")

        payload = self.get_json(
            f"{API_BASE}/search",
            params={
                "key": self.api_key,
                "part": "snippet",
                "channelId": channel_id,
                "q": query,
                "type": "video",
                "maxResults": min(limit, 10),
                "order": "relevance",
            },
            cache_key=f"yt:search:{channel_id}:{query}:{limit}",
        )

        if isinstance(payload, dict) and payload.get("error"):
            message = payload["error"].get("message", "YouTube API error")
            raise NotAvailable(self.service_name, message)

        candidates: list[VideoCandidate] = []
        for item in (payload or {}).get("items", []):
            video_id = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}
            if not video_id:
                continue
            candidates.append(
                VideoCandidate(
                    external_id=video_id,
                    title=snippet.get("title", ""),
                    channel_id=snippet.get("channelId", channel_id),
                    channel_title=snippet.get("channelTitle", ""),
                    published_at=_parse_time(snippet.get("publishedAt")),
                    thumbnail_url=(
                        (snippet.get("thumbnails") or {}).get("medium") or {}
                    ).get("url"),
                )
            )
        return candidates

    def hydrate_durations(self, candidates: list[VideoCandidate]) -> None:
        """Fill in durations, which `search` does not return."""
        if not candidates or not self.configured:
            return
        ids = ",".join(c.external_id for c in candidates[:50])
        try:
            payload = self.get_json(
                f"{API_BASE}/videos",
                params={"key": self.api_key, "part": "contentDetails", "id": ids},
                cache_key=f"yt:videos:{ids}",
            )
        except NotAvailable:
            return

        durations = {
            item.get("id"): parse_duration(
                (item.get("contentDetails") or {}).get("duration")
            )
            for item in (payload or {}).get("items", [])
        }
        for candidate in candidates:
            candidate.duration_seconds = durations.get(candidate.external_id)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def score_candidate(
    candidate: VideoCandidate,
    *,
    problem_title: str,
    external_id: str,
    platform: str,
    channel_weight: float = 1.0,
) -> tuple[float, dict[str, float]]:
    """Score a video against the problem it is supposed to explain.

    Deliberately ignores view count: a popular video about a different problem
    is worse than an obscure one about the right problem.
    """
    title = (candidate.title or "").lower()
    breakdown: dict[str, float] = {}

    # An exact problem-id match is the single strongest signal.
    ident = external_id.lower()
    if ident and ident in re.sub(r"[\s\-_/]", "", title):
        breakdown["problem_id_match"] = 4.0
    elif ident and ident in title:
        breakdown["problem_id_match"] = 3.5

    # Title overlap, ignoring short filler words.
    problem_words = {
        w for w in re.findall(r"[a-z0-9]+", (problem_title or "").lower()) if len(w) > 2
    }
    if problem_words:
        overlap = len({w for w in problem_words if w in title}) / len(problem_words)
        breakdown["title_overlap"] = round(overlap * 3.0, 3)
        if overlap == 1.0:
            breakdown["exact_title"] = 1.5

    breakdown["trusted_channel"] = 2.0 * channel_weight

    if platform and platform.lower() in title:
        breakdown["platform_match"] = 0.5

    if candidate.duration_seconds is not None:
        if MIN_SENSIBLE_SECONDS <= candidate.duration_seconds <= MAX_SENSIBLE_SECONDS:
            breakdown["duration_sane"] = 0.5
        else:
            # A 30-second short is not an editorial.
            breakdown["duration_sane"] = -1.0

    if candidate.published_at:
        age_years = (
            datetime.now(timezone.utc) - candidate.published_at
        ).days / 365.25
        breakdown["recency"] = round(max(0.0, 0.75 - age_years * 0.1), 3)

    return round(sum(breakdown.values()), 3), breakdown
