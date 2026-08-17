"""Codeforces integration — official REST API only, no scraping.

Endpoints used:
    GET /api/user.status?handle=&from=&count=   submissions
    GET /api/problemset.problems                the full problem archive
    GET /api/user.info?handles=                 rating snapshot
    GET /api/user.rating?handle=                rating history
    GET /api/contest.list                       contest metadata

Codeforces asks for at most one request per two seconds; `min_interval`
enforces that so a sync cannot get the user IP-banned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.base import BaseClient, NotAvailable
from app.models.enums import Platform
from app.utils.normalize import ProblemRef, normalize_codeforces_id

log = get_logger(__name__)


@dataclass
class ExternalSubmission:
    """Platform-agnostic submission, ready for ingestion."""

    external_id: str
    problem_ref: ProblemRef
    submitted_at: datetime
    verdict: str
    is_accepted: bool
    language: str | None = None
    runtime_ms: int | None = None
    memory_kb: int | None = None
    during_contest: bool = False
    external_contest_id: str | None = None
    problem_metadata: dict[str, Any] | None = None


class CodeforcesClient(BaseClient):
    service_name = "Codeforces"
    #: The documented limit is one call per two seconds.
    min_interval = 2.1
    default_cache_ttl = 300.0

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.base = settings.codeforces_api_base.rstrip("/")

    def _call(self, method: str, params: dict[str, Any], **kwargs) -> Any:
        payload = self.get_json(f"{self.base}/{method}", params=params, **kwargs)
        if not isinstance(payload, dict):
            raise NotAvailable(self.service_name, "Unexpected response shape")
        if payload.get("status") != "OK":
            comment = payload.get("comment", "unknown error")
            # A bad handle is a user error, not an outage — surface it clearly.
            raise NotAvailable(self.service_name, f"Codeforces: {comment}")
        return payload.get("result")

    # -- account -----------------------------------------------------------

    def fetch_user_info(self, handle: str) -> dict[str, Any] | None:
        result = self._call(
            "user.info",
            {"handles": handle},
            cache_key=f"cf:user.info:{handle}",
            cache_ttl=600,
        )
        if not result:
            return None
        user = result[0]
        return {
            "handle": user.get("handle"),
            "rating": user.get("rating"),
            "max_rating": user.get("maxRating"),
            "rank": user.get("rank"),
            "max_rank": user.get("maxRank"),
        }

    def fetch_submissions(
        self, handle: str, *, limit: int = 2000, start: int = 1
    ) -> list[ExternalSubmission]:
        """Newest-first submission history."""
        result = self._call(
            "user.status",
            {"handle": handle, "from": start, "count": limit},
            cache_key=f"cf:user.status:{handle}:{start}:{limit}",
            cache_ttl=120,
        )
        submissions: list[ExternalSubmission] = []
        for row in result or []:
            parsed = self._parse_submission(row)
            if parsed is not None:
                submissions.append(parsed)
        return submissions

    def _parse_submission(self, row: dict[str, Any]) -> ExternalSubmission | None:
        problem = row.get("problem") or {}
        contest_id = problem.get("contestId")
        index = problem.get("index")
        if contest_id is None or not index:
            # Problems outside the archive (e.g. some gym entries) have no
            # stable canonical id; skipping them beats creating a phantom.
            return None

        try:
            external_id = normalize_codeforces_id(contest_id, index)
        except (ValueError, TypeError):
            return None

        verdict = row.get("verdict") or "UNKNOWN"
        author = row.get("author") or {}
        participant_type = author.get("participantType", "")

        return ExternalSubmission(
            external_id=str(row.get("id")),
            problem_ref=ProblemRef(
                platform=Platform.CODEFORCES,
                external_id=external_id,
                contest_id=int(contest_id),
                index=str(index).upper(),
                title=problem.get("name"),
            ),
            submitted_at=datetime.fromtimestamp(
                row.get("creationTimeSeconds", 0), tz=timezone.utc
            ),
            verdict=verdict,
            is_accepted=verdict == "OK",
            language=row.get("programmingLanguage"),
            runtime_ms=row.get("timeConsumedMillis"),
            memory_kb=(row.get("memoryConsumedBytes") or 0) // 1024 or None,
            during_contest=participant_type == "CONTESTANT",
            external_contest_id=str(contest_id),
            problem_metadata={
                "title": problem.get("name"),
                "rating": problem.get("rating"),
                "tags": problem.get("tags") or [],
            },
        )

    def fetch_rating_history(self, handle: str) -> list[dict[str, Any]]:
        result = self._call(
            "user.rating",
            {"handle": handle},
            cache_key=f"cf:user.rating:{handle}",
            cache_ttl=600,
        )
        return [
            {
                "contest_id": str(row.get("contestId")),
                "contest_name": row.get("contestName"),
                "rank": row.get("rank"),
                "rating_before": row.get("oldRating"),
                "rating_after": row.get("newRating"),
                "rating_change": (row.get("newRating") or 0) - (row.get("oldRating") or 0),
                "at": datetime.fromtimestamp(
                    row.get("ratingUpdateTimeSeconds", 0), tz=timezone.utc
                ),
            }
            for row in result or []
        ]

    # -- problem archive ---------------------------------------------------

    def fetch_problemset(self) -> dict[str, dict[str, Any]]:
        """The entire archive keyed by canonical id.

        One call gives authoritative titles, ratings and tags for every
        problem, which is how sheet imports avoid hand-maintained metadata.
        """
        result = self._call(
            "problemset.problems",
            {},
            cache_key="cf:problemset",
            cache_ttl=3600 * 6,
        )
        problems = (result or {}).get("problems", [])
        statistics = {
            f"{s.get('contestId')}{s.get('index')}": s.get("solvedCount")
            for s in (result or {}).get("problemStatistics", [])
        }

        archive: dict[str, dict[str, Any]] = {}
        for problem in problems:
            contest_id = problem.get("contestId")
            index = problem.get("index")
            if contest_id is None or not index:
                continue
            key = f"{contest_id}{str(index).upper()}"
            archive[key] = {
                "external_id": key,
                "title": problem.get("name"),
                "rating": problem.get("rating"),
                "tags": problem.get("tags") or [],
                "contest_id": int(contest_id),
                "index": str(index).upper(),
                "solved_count": statistics.get(key),
            }
        return archive

    def fetch_problem_metadata(self, ref: ProblemRef) -> dict[str, Any] | None:
        """Metadata for one problem, sourced from the cached archive."""
        archive = self.fetch_problemset()
        entry = archive.get(ref.external_id)
        if entry is None:
            return None
        return {
            "title": entry["title"],
            "rating": entry["rating"],
            "rating_source": "codeforces",
            "tags": entry["tags"],
            "solved_count": entry.get("solved_count"),
        }

    def fetch_contests(self, gym: bool = False) -> list[dict[str, Any]]:
        result = self._call(
            "contest.list",
            {"gym": str(gym).lower()},
            cache_key=f"cf:contest.list:{gym}",
            cache_ttl=3600,
        )
        return [
            {
                "external_id": str(row.get("id")),
                "name": row.get("name"),
                "start_time": datetime.fromtimestamp(
                    row["startTimeSeconds"], tz=timezone.utc
                )
                if row.get("startTimeSeconds")
                else None,
                "duration_seconds": row.get("durationSeconds"),
                "type": row.get("type"),
                "phase": row.get("phase"),
            }
            for row in result or []
        ]
