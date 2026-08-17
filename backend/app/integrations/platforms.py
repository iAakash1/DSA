"""The four platform connectors.

Each declares only the capabilities its sources genuinely support. The
differences are real and were verified against the live endpoints rather than
assumed:

* **Codeforces** — an official, documented, complete public API. Everything.
* **AtCoder** — no official stats API, but `atcoder.jp/users/<u>/history/json`
  is official and carries the full rated contest history, so rating, peak
  rating and contest count are all derivable from the platform itself. Solved
  counts come from the kenkoooo AtCoder Problems index, a community service,
  and are labelled as such. (Its `/v3/user/rating` route returns 404 and is
  deliberately not used.)
* **LeetCode** — no official API at all. The GraphQL endpoint the site itself
  uses works and is what the existing client already speaks, but it is
  unofficial and can change without notice, so the connector is marked
  `unofficial` and its failures degrade one card.
* **CodeChef** — no reliable public API. The official profile is HTML only and
  the widely-used community API is dead. Scraping was considered and rejected:
  it is fragile and not ours to do. CodeChef is therefore connect-only, and
  says so, rather than pretending to statistics it cannot obtain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.integrations.base import BaseClient, IntegrationError, NotAvailable
from app.integrations.codeforces import CodeforcesClient
from app.integrations.connectors import (
    Capability,
    ContestResult,
    PlatformConnector,
    PlatformProfile,
    ProfileNotFound,
    Provenance,
    register,
)
from app.integrations.leetcode import LeetCodeClient
from app.models.enums import Platform


# ---------------------------------------------------------------------------
# Codeforces — official API, full coverage
# ---------------------------------------------------------------------------


class CodeforcesConnector(PlatformConnector):
    platform = Platform.CODEFORCES
    label = "Codeforces"
    unofficial = False
    capabilities = frozenset(
        {
            Capability.RATING,
            Capability.MAX_RATING,
            Capability.RANK,
            Capability.PROBLEMS_SOLVED,
            Capability.CONTEST_HISTORY,
            Capability.SUBMISSION_HISTORY,
            Capability.PROFILE_VALIDATION,
        }
    )

    def __init__(self) -> None:
        self._client = CodeforcesClient()

    def profile_url(self, username: str) -> str:
        return f"https://codeforces.com/profile/{username}"

    def validate_username(self, username: str) -> bool:
        return self._client.fetch_user_info(username) is not None

    def fetch_profile(self, username: str) -> PlatformProfile:
        info = self._client.fetch_user_info(username)
        if info is None:
            raise ProfileNotFound(self.platform, username)

        solved = None
        contests = None
        try:
            # Distinct accepted problems, not accepted submissions — a user who
            # resubmits the same problem has not solved it twice.
            subs = self._client.fetch_submissions(username)
            solved = len({s.external_id for s in subs if s.is_accepted})
        except IntegrationError:
            pass
        try:
            contests = len(self._client.fetch_rating_history(username))
        except IntegrationError:
            pass

        profile = PlatformProfile(
            platform=self.platform,
            username=info.get("handle", username),
            profile_url=self.profile_url(username),
            rating=info.get("rating"),
            max_rating=info.get("maxRating"),
            rank=info.get("rank"),
            problems_solved=solved,
            contests_participated=contests,
        )
        for key in ("rating", "max_rating", "rank", "problems_solved", "contests_participated"):
            if getattr(profile, key) is not None:
                profile.provenance[key] = Provenance.OFFICIAL
        if solved is None:
            profile.limitations.append("Submission history was unreachable; solved count not updated.")
        return profile

    def fetch_contests(self, username: str) -> list[ContestResult]:
        out: list[ContestResult] = []
        for row in self._client.fetch_rating_history(username):
            ts = row.get("ratingUpdateTimeSeconds")
            out.append(
                ContestResult(
                    external_id=str(row.get("contestId")),
                    name=row.get("contestName", ""),
                    ended_at=datetime.fromtimestamp(ts, UTC) if ts else None,
                    rank=row.get("rank"),
                    old_rating=row.get("oldRating"),
                    new_rating=row.get("newRating"),
                )
            )
        return out

    def fetch_solved_problem_ids(self, username: str) -> list[str]:
        return sorted(
            {s.external_id for s in self._client.fetch_submissions(username) if s.is_accepted}
        )


# ---------------------------------------------------------------------------
# AtCoder — official contest history, community solved counts
# ---------------------------------------------------------------------------


class AtCoderClient(BaseClient):
    service_name = "atcoder"
    #: AtCoder and the community index are both small volunteer-run services.
    min_interval = 1.5

    OFFICIAL_HISTORY = "https://atcoder.jp/users/{user}/history/json"
    OFFICIAL_PROFILE = "https://atcoder.jp/users/{user}"
    COMMUNITY_AC_RANK = "https://kenkoooo.com/atcoder/atcoder-api/v3/user/ac_rank"

    def profile_exists(self, username: str) -> bool:
        """Whether the handle exists, from the profile page's status code.

        The history endpoint cannot answer this: it returns `200 []` for an
        unknown user, which is byte-identical to a real user who has not yet
        entered a rated contest. Accepting that as proof would let anyone
        "connect" a handle that does not exist. Only the HTTP status is read —
        the page body is never parsed.
        """
        try:
            response = self.request("GET", self.OFFICIAL_PROFILE.format(user=username))
        except NotAvailable:
            raise
        return response.status_code == 200

    def fetch_history(self, username: str) -> list[dict[str, Any]] | None:
        """Official rated-contest history. `None` when the user does not exist."""
        try:
            data = self.get_json(self.OFFICIAL_HISTORY.format(user=username))
        except NotAvailable:
            return None
        return data if isinstance(data, list) else None

    def fetch_solved_count(self, username: str) -> tuple[int | None, str | None]:
        """Accepted-problem count from the community index.

        Returns `(count, reason_unavailable)`. The two failure modes are
        different and must not be reported identically: a 404 means the index
        has no entry for this user — it only tracks handles with accepted
        submissions — whereas anything else means the service itself is
        struggling. Telling someone the index is down when they simply are not
        in it yet sends them chasing an outage that is not happening.

        Community-sourced either way, so failure never invalidates the rest of
        the profile, which comes from AtCoder itself.
        """
        try:
            response = self.request(
                "GET",
                self.COMMUNITY_AC_RANK,
                params={"user": username},
                cache_key=f"ac:rank:{username}",
                cache_ttl=600,
            )
        except IntegrationError:
            return None, "unreachable"

        if response.status_code == 404:
            return None, "not_indexed"
        if response.status_code != 200:
            return None, "unreachable"
        try:
            data = response.json()
        except ValueError:
            return None, "unreachable"
        if isinstance(data, dict) and isinstance(data.get("count"), int):
            return data["count"], None
        return None, "unreachable"


class AtCoderConnector(PlatformConnector):
    platform = "atcoder"
    label = "AtCoder"
    #: Ratings and contests are official; only the solved count is not.
    unofficial = False
    capabilities = frozenset(
        {
            Capability.RATING,
            Capability.MAX_RATING,
            Capability.CONTEST_HISTORY,
            Capability.PROBLEMS_SOLVED,
            Capability.PROFILE_VALIDATION,
        }
    )

    def __init__(self) -> None:
        self._client = AtCoderClient()

    def profile_url(self, username: str) -> str:
        return f"https://atcoder.jp/users/{username}"

    def validate_username(self, username: str) -> bool:
        return self._client.profile_exists(username)

    def fetch_profile(self, username: str) -> PlatformProfile:
        if not self._client.profile_exists(username):
            raise ProfileNotFound(self.platform, username)
        history = self._client.fetch_history(username) or []

        rated = [row for row in history if row.get("IsRated")]
        rating = rated[-1].get("NewRating") if rated else None
        max_rating = max((row.get("NewRating") or 0) for row in rated) if rated else None
        solved, solved_unavailable = self._client.fetch_solved_count(username)

        profile = PlatformProfile(
            platform=self.platform,
            username=username,
            profile_url=self.profile_url(username),
            rating=rating,
            max_rating=max_rating,
            problems_solved=solved,
            contests_participated=len(rated) or None,
        )
        for key in ("rating", "max_rating", "contests_participated"):
            if getattr(profile, key) is not None:
                profile.provenance[key] = Provenance.OFFICIAL
        if solved is not None:
            profile.provenance["problems_solved"] = Provenance.COMMUNITY
        elif solved_unavailable == "not_indexed":
            profile.limitations.append(
                "AtCoder publishes no solved-problem count. The community index "
                "used for it has no entry for this handle yet — it lists users "
                "once they have accepted submissions. Rating and contests are "
                "official and unaffected."
            )
        else:
            profile.limitations.append(
                "The community index used for solved counts is unreachable "
                "right now. Rating and contest history are official and "
                "unaffected."
            )
        if not rated:
            profile.limitations.append("No rated contests yet, so there is no rating.")
        return profile

    def fetch_contests(self, username: str) -> list[ContestResult]:
        history = self._client.fetch_history(username) or []
        out: list[ContestResult] = []
        for row in history:
            ended = row.get("EndTime")
            try:
                ended_at = datetime.fromisoformat(ended) if ended else None
            except ValueError:
                ended_at = None
            out.append(
                ContestResult(
                    external_id=str(row.get("ContestScreenName") or row.get("ContestName")),
                    name=row.get("ContestName", ""),
                    ended_at=ended_at,
                    rank=row.get("Place"),
                    old_rating=row.get("OldRating"),
                    new_rating=row.get("NewRating"),
                    is_rated=bool(row.get("IsRated")),
                )
            )
        return out


# ---------------------------------------------------------------------------
# LeetCode — unofficial GraphQL
# ---------------------------------------------------------------------------


class LeetCodeConnector(PlatformConnector):
    platform = Platform.LEETCODE
    label = "LeetCode"
    #: No official API exists. The endpoint is the site's own GraphQL, which
    #: can change without notice — hence quarantined behind this connector.
    unofficial = True
    capabilities = frozenset(
        {
            Capability.PROBLEMS_SOLVED,
            Capability.DIFFICULTY_BREAKDOWN,
            Capability.SUBMISSION_HISTORY,
            Capability.RANK,
            Capability.PROFILE_VALIDATION,
        }
    )

    def __init__(self) -> None:
        self._client = LeetCodeClient()

    def profile_url(self, username: str) -> str:
        return f"https://leetcode.com/u/{username}/"

    def validate_username(self, username: str) -> bool:
        return self._client.fetch_user_info(username) is not None

    def fetch_profile(self, username: str) -> PlatformProfile:
        info = self._client.fetch_user_info(username)
        if info is None:
            raise ProfileNotFound(self.platform, username)

        solved = info.get("solved") or {}
        breakdown = {
            key: solved[key] for key in ("easy", "medium", "hard") if key in solved
        }
        ranking = info.get("ranking")

        profile = PlatformProfile(
            platform=self.platform,
            username=info.get("username", username),
            profile_url=self.profile_url(username),
            problems_solved=solved.get("all"),
            difficulty_breakdown=breakdown or None,
            # A global ranking, not a title. Formatted so it cannot be mistaken
            # for a rating by anything downstream.
            rank=f"#{ranking:,}" if isinstance(ranking, int) else None,
        )
        for key in ("problems_solved", "difficulty_breakdown", "rank"):
            if getattr(profile, key) is not None:
                profile.provenance[key] = Provenance.COMMUNITY
        profile.limitations.append(
            "LeetCode publishes no official API; these figures come from the "
            "site's own GraphQL endpoint and may change without notice. "
            "Contest rating is not read, as no reliable public source exposes it."
        )
        return profile


# ---------------------------------------------------------------------------
# CodeChef — connect-only, by decision
# ---------------------------------------------------------------------------


class CodeChefConnector(PlatformConnector):
    platform = "codechef"
    label = "CodeChef"
    unofficial = False
    #: Deliberately empty of statistics. CodeChef publishes no usable public
    #: API: the profile page is HTML only, and the community API that most
    #: projects relied on is offline. Scraping was rejected rather than
    #: shipped, so the honest capability set is "we can store your handle".
    capabilities = frozenset()

    def profile_url(self, username: str) -> str:
        return f"https://www.codechef.com/users/{username}"

    def validate_username(self, username: str) -> bool:
        # No capability to check, so the handle is accepted as given rather
        # than blocking a real user on a check that cannot be performed.
        return True

    def fetch_profile(self, username: str) -> PlatformProfile:
        profile = PlatformProfile(
            platform=self.platform,
            username=username,
            profile_url=self.profile_url(username),
        )
        profile.limitations.append(
            "CodeChef offers no public API, so rating, solved count and contest "
            "history cannot be imported. The profile link is saved and kept up "
            "to date; statistics will appear here if CodeChef publishes an API."
        )
        return profile


CODEFORCES = register(CodeforcesConnector())
ATCODER = register(AtCoderConnector())
LEETCODE = register(LeetCodeConnector())
CODECHEF = register(CodeChefConnector())
