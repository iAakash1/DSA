"""LeetCode integration — public GraphQL endpoint.

Documented limitations (verified behaviour, not assumptions from a tutorial):

* `recentAcSubmissionList` returns only the most recent ~20 accepted
  submissions. It is a *delta* feed, not a history. Full history requires an
  authenticated session cookie, which CP-Forge deliberately does not ask for.
* Consequently a first-time sync cannot reconstruct years of LeetCode history.
  `fetch_solved_problem_slugs` is used to backfill status (via the public
  profile's solved list where exposed), and `scripts/import_leetcode.py`
  accepts an exported JSON/CSV for a complete one-off backfill.
* LeetCode rate-limits aggressively and rejects requests without a browser-like
  Referer header.

Everything degrades: if LeetCode is unreachable, existing data is untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.base import BaseClient, NotAvailable
from app.integrations.codeforces import ExternalSubmission
from app.models.enums import Platform
from app.utils.normalize import ProblemRef, normalize_difficulty

log = get_logger(__name__)

_RECENT_AC_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
}
"""

_QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    title
    titleSlug
    difficulty
    isPaidOnly
    acRate
    topicTags { name slug }
  }
}
"""

_USER_PROFILE_QUERY = """
query userProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile { ranking reputation }
    submitStatsGlobal {
      acSubmissionNum { difficulty count }
      totalSubmissionNum { difficulty count }
    }
  }
}
"""


class LeetCodeClient(BaseClient):
    service_name = "LeetCode"
    min_interval = 0.6
    default_cache_ttl = 300.0

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.url = settings.leetcode_graphql_url

    def _graphql(
        self,
        query: str,
        variables: dict[str, Any],
        *,
        cache_key: str | None = None,
        cache_ttl: float | None = None,
    ) -> dict[str, Any]:
        payload = self.post_json(
            self.url,
            json={"query": query, "variables": variables},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://leetcode.com",
                "Origin": "https://leetcode.com",
                "User-Agent": "CP-Forge/1.0 (personal practice tracker)",
            },
            cache_key=cache_key,
            cache_ttl=cache_ttl,
        )
        if not isinstance(payload, dict):
            raise NotAvailable(self.service_name, "Unexpected response shape")
        if payload.get("errors"):
            message = payload["errors"][0].get("message", "GraphQL error")
            raise NotAvailable(self.service_name, f"LeetCode: {message}")
        return payload.get("data") or {}

    def fetch_user_info(self, username: str) -> dict[str, Any] | None:
        data = self._graphql(
            _USER_PROFILE_QUERY,
            {"username": username},
            cache_key=f"lc:user:{username}",
            cache_ttl=600,
        )
        user = data.get("matchedUser")
        if not user:
            return None

        stats = user.get("submitStatsGlobal") or {}
        solved = {
            row["difficulty"].lower(): row["count"]
            for row in stats.get("acSubmissionNum", [])
        }
        return {
            "username": user.get("username"),
            "ranking": (user.get("profile") or {}).get("ranking"),
            "solved": solved,
        }

    def fetch_submissions(
        self, username: str, *, limit: int = 20
    ) -> list[ExternalSubmission]:
        """Recent accepted submissions.

        Capped at 20 by LeetCode regardless of the requested limit — this is a
        rolling window, so syncing regularly is what keeps history complete.
        """
        data = self._graphql(
            _RECENT_AC_QUERY,
            {"username": username, "limit": min(limit, 20)},
            cache_key=f"lc:recent:{username}:{limit}",
            cache_ttl=120,
        )
        rows = data.get("recentAcSubmissionList") or []

        submissions: list[ExternalSubmission] = []
        for row in rows:
            slug = row.get("titleSlug")
            if not slug:
                continue
            timestamp = int(row.get("timestamp") or 0)
            submissions.append(
                ExternalSubmission(
                    external_id=str(row.get("id")),
                    problem_ref=ProblemRef(
                        platform=Platform.LEETCODE,
                        external_id=slug,
                        slug=slug,
                        title=row.get("title"),
                    ),
                    submitted_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                    verdict="Accepted",
                    is_accepted=True,
                    problem_metadata={"title": row.get("title")},
                )
            )
        return submissions

    def fetch_problem_metadata(self, ref: ProblemRef) -> dict[str, Any] | None:
        slug = ref.slug or ref.external_id
        data = self._graphql(
            _QUESTION_QUERY,
            {"titleSlug": slug},
            cache_key=f"lc:question:{slug}",
            cache_ttl=3600 * 24,
        )
        question = data.get("question")
        if not question:
            return None

        return {
            "title": question.get("title"),
            "difficulty": normalize_difficulty(question.get("difficulty")),
            "tags": [t.get("slug") for t in question.get("topicTags") or [] if t.get("slug")],
            "acceptance_rate": question.get("acRate"),
            "is_premium": bool(question.get("isPaidOnly")),
            "extra": {"frontend_id": question.get("questionFrontendId")},
        }
