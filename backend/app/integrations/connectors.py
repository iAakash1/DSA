"""A common interface over the competitive-programming platforms.

Four platforms expose wildly different amounts of data, through sources of
wildly different reliability. The point of this layer is that the rest of
CP-Forge never has to know which is which: it asks a connector what it
*supports*, calls only that, and renders "Unavailable" for the rest.

The honesty rules this layer enforces:

* A capability the platform cannot serve reliably is declared unsupported, and
  the corresponding field stays `None`. Nothing is estimated, and `None` never
  becomes `0`.
* Every field records where it came from. `Provenance.OFFICIAL` and
  `Provenance.COMMUNITY` are not interchangeable — AtCoder's ratings come from
  AtCoder itself, its solved counts from a third-party index, and the UI is
  entitled to say so.
* Connectors are built on `BaseClient`, so they inherit its timeouts, backoff,
  minimum call interval and TTL cache. An unofficial upstream going down
  degrades one card, never the application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.integrations.base import IntegrationError


class Capability(StrEnum):
    """What a platform can actually be asked for.

    Declared per connector rather than assumed, so adding a platform with
    partial coverage is a first-class case rather than a special case.
    """

    RATING = "rating"
    MAX_RATING = "max_rating"
    RANK = "rank"
    PROBLEMS_SOLVED = "problems_solved"
    DIFFICULTY_BREAKDOWN = "difficulty_breakdown"
    CONTEST_HISTORY = "contest_history"
    SUBMISSION_HISTORY = "submission_history"
    PROFILE_VALIDATION = "profile_validation"


class Provenance(StrEnum):
    """How trustworthy a value's source is.

    Kept per field, not per platform: AtCoder's rating is official while its
    solved count is community-indexed, and collapsing that distinction would
    misrepresent both.
    """

    OFFICIAL = "official"
    COMMUNITY = "community"


@dataclass
class PlatformProfile:
    """A normalized profile snapshot.

    Every statistic is optional. `None` means "this platform does not expose
    it reliably", which the UI renders as Unavailable — it is never rendered
    as zero, because a user with no rating and a platform with no rating API
    are not the same thing.
    """

    platform: str
    username: str
    profile_url: str
    external_id: str | None = None

    rating: int | None = None
    max_rating: int | None = None
    rank: str | None = None
    problems_solved: int | None = None
    contests_participated: int | None = None
    #: e.g. {"easy": 120, "medium": 240, "hard": 30}
    difficulty_breakdown: dict[str, int] | None = None

    #: field name -> Provenance, for the fields that are populated.
    provenance: dict[str, str] = field(default_factory=dict)
    #: Human-readable notes about what could not be fetched and why.
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "username": self.username,
            "profile_url": self.profile_url,
            "external_id": self.external_id,
            "rating": self.rating,
            "max_rating": self.max_rating,
            "rank": self.rank,
            "problems_solved": self.problems_solved,
            "contests_participated": self.contests_participated,
            "difficulty_breakdown": self.difficulty_breakdown,
            "provenance": self.provenance,
            "limitations": self.limitations,
        }


@dataclass
class ContestResult:
    """One rated contest, normalized across platforms."""

    external_id: str
    name: str
    ended_at: datetime | None
    rank: int | None = None
    old_rating: int | None = None
    new_rating: int | None = None
    is_rated: bool = True

    @property
    def rating_change(self) -> int | None:
        if self.old_rating is None or self.new_rating is None:
            return None
        return self.new_rating - self.old_rating


class ProfileNotFound(IntegrationError):
    """The handle does not exist on that platform.

    Distinct from `NotAvailable`: a typo is the user's to fix, an outage is
    not, and the UI must not tell someone their handle is wrong when the
    upstream is merely down.
    """

    def __init__(self, service: str, username: str) -> None:
        super().__init__(service, f"No {service} profile found for {username!r}")
        self.username = username


class PlatformConnector:
    """Base class. Subclasses declare capabilities and implement only those.

    Anything not declared in `capabilities` raises `NotImplementedError` if
    called, so a caller that ignores the capability set fails loudly in tests
    rather than silently returning empty data in production.
    """

    #: Value stored in `platform_accounts.platform` and `problems.platform`.
    platform: str = ""
    #: Display name for the UI.
    label: str = ""
    capabilities: frozenset[Capability] = frozenset()
    #: Set when the platform has no official API and the integration depends on
    #: an unofficial or third-party source. Surfaced in the UI.
    unofficial: bool = False

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def profile_url(self, username: str) -> str:
        raise NotImplementedError

    def validate_username(self, username: str) -> bool:
        """Whether the handle exists.

        Connectors that cannot check this declare no `PROFILE_VALIDATION`
        capability and return True — accepting the handle unverified is
        better than blocking a real user over a check we cannot perform.
        """
        return True

    def fetch_profile(self, username: str) -> PlatformProfile:
        """The normalized snapshot. Every connector implements this."""
        raise NotImplementedError

    def fetch_contests(self, username: str) -> list[ContestResult]:
        raise NotImplementedError

    def fetch_solved_problem_ids(self, username: str) -> list[str]:
        """External problem ids the user has solved, for canonical mapping."""
        raise NotImplementedError


_REGISTRY: dict[str, PlatformConnector] = {}


def register(connector: PlatformConnector) -> PlatformConnector:
    _REGISTRY[connector.platform] = connector
    return connector


def get_connector(platform: str) -> PlatformConnector:
    connector = _REGISTRY.get(platform.strip().lower())
    if connector is None:
        raise IntegrationError(platform, f"No connector registered for {platform!r}")
    return connector


def all_connectors() -> list[PlatformConnector]:
    return list(_REGISTRY.values())


def connector_catalogue() -> list[dict[str, Any]]:
    """What the UI needs to render the Coding Profiles cards honestly."""
    return [
        {
            "platform": c.platform,
            "label": c.label,
            "unofficial": c.unofficial,
            "capabilities": sorted(str(cap) for cap in c.capabilities),
        }
        for c in all_connectors()
    ]
