"""Problem identity normalization.

The same problem arrives from many shapes:

    Codeforces:  1400B, 1400/B, 1400-B, contest 1400 index B,
                 https://codeforces.com/problemset/problem/1400/B
                 https://codeforces.com/contest/1400/problem/B
    LeetCode:    two-sum, Two Sum, 1,
                 https://leetcode.com/problems/two-sum/description/

All of them must collapse to one canonical identity, or the database quietly
fills with duplicates and every statistic becomes wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from app.models.enums import Difficulty, Platform


class NormalizationError(ValueError):
    """Raised when an input cannot be resolved to a canonical problem."""


@dataclass(frozen=True)
class ProblemRef:
    """A canonical, deduplicated reference to a problem."""

    platform: str
    external_id: str
    slug: str | None = None
    title: str | None = None
    contest_id: int | None = None
    index: str | None = None

    @property
    def canonical_id(self) -> str:
        return f"{self.platform}:{self.external_id}"

    @property
    def url(self) -> str:
        if self.platform == Platform.TAKEUFORWARD:
            # The numeric external_id is the identity; the slug is only a link
            # hint, because takeUforward reuses slugs across distinct problems.
            if self.slug:
                return f"https://takeuforward.org/plus/dsa/problems/{self.slug}"
            return "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2"
        if self.platform == Platform.CODEFORCES:
            if self.contest_id is not None and self.index:
                # Gym/ICPC contests use a different path; problemset covers the
                # regular archive and redirects correctly for contest problems.
                return (
                    f"https://codeforces.com/problemset/problem/"
                    f"{self.contest_id}/{self.index}"
                )
            return "https://codeforces.com/problemset"
        return f"https://leetcode.com/problems/{self.slug or self.external_id}/"


_CF_URL_PROBLEMSET = re.compile(
    r"codeforces\.com/problemset/problem/(?P<contest>\d+)/(?P<index>[A-Za-z]\d*)",
    re.IGNORECASE,
)
_CF_URL_CONTEST = re.compile(
    r"codeforces\.com/(?:contest|gym)/(?P<contest>\d+)/problem/(?P<index>[A-Za-z]\d*)",
    re.IGNORECASE,
)
_CF_BARE = re.compile(r"^(?P<contest>\d{1,6})[\s/\-_]?(?P<index>[A-Za-z]\d?)$")
_LC_URL = re.compile(r"leetcode\.com/problems/(?P<slug>[a-z0-9\-]+)", re.IGNORECASE)
#: Premium problems are linked through the sign-in page, which carries the real
#: problem path in `next=`. Reading it is plain URL parsing — the problem is
#: still premium and still requires the user's own LeetCode account.
_LC_LOGIN_NEXT = re.compile(
    r"leetcode\.com/accounts/login/?\?[^#]*next=(?P<next>[^&#]+)", re.IGNORECASE
)
#: takeUforward's own problems, identified by the numeric id the sheet assigns.
_TUF_ID = re.compile(r"^tuf[-:]?(?P<id>\d+)$", re.IGNORECASE)


def slugify(text: str) -> str:
    """LeetCode-compatible slug: lowercase, hyphen-separated, alnum only."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-]", "", text or "").strip().lower()
    return re.sub(r"[\s\-]+", "-", cleaned).strip("-")


def normalize_codeforces_id(contest_id: int | str, index: str) -> str:
    """Canonical Codeforces id: `1400B` — contest number + uppercase index."""
    idx = str(index).strip().upper()
    if not idx:
        raise NormalizationError("Codeforces problem index is required")
    return f"{int(contest_id)}{idx}"


def parse_codeforces(value: str) -> ProblemRef:
    raw = (value or "").strip()
    if not raw:
        raise NormalizationError("Empty Codeforces reference")

    for pattern in (_CF_URL_PROBLEMSET, _CF_URL_CONTEST):
        m = pattern.search(raw)
        if m:
            contest = int(m.group("contest"))
            index = m.group("index").upper()
            return ProblemRef(
                platform=Platform.CODEFORCES,
                external_id=normalize_codeforces_id(contest, index),
                contest_id=contest,
                index=index,
            )

    m = _CF_BARE.match(raw.replace(" ", ""))
    if m:
        contest = int(m.group("contest"))
        index = m.group("index").upper()
        return ProblemRef(
            platform=Platform.CODEFORCES,
            external_id=normalize_codeforces_id(contest, index),
            contest_id=contest,
            index=index,
        )

    raise NormalizationError(f"Could not parse a Codeforces problem from {value!r}")


def parse_takeuforward(value: str, *, title: str | None = None) -> ProblemRef:
    """Canonical identity for a takeUforward-native problem.

    The identity is the numeric problem id the sheet publishes, never the URL
    slug: takeUforward serves several genuinely different problems under one
    slug (`.../problems/cpp` is both "Cpp Basics" and "What are arrays,
    strings?"), so slug-keyed identity would silently merge them into one row
    and lose a problem from the sheet.
    """
    raw = (value or "").strip()
    if not raw:
        raise NormalizationError("Empty takeUforward reference")

    m = _TUF_ID.match(raw)
    if m:
        return ProblemRef(
            platform=Platform.TAKEUFORWARD, external_id=m.group("id"), title=title
        )
    if raw.isdigit():
        return ProblemRef(platform=Platform.TAKEUFORWARD, external_id=raw, title=title)

    raise NormalizationError(
        f"takeUforward problems are identified by their numeric sheet id, got {value!r}"
    )


def parse_leetcode(value: str) -> ProblemRef:
    raw = (value or "").strip()
    if not raw:
        raise NormalizationError("Empty LeetCode reference")

    login = _LC_LOGIN_NEXT.search(raw)
    if login:
        raw = "https://leetcode.com" + unquote(login.group("next"))

    m = _LC_URL.search(raw)
    if m:
        slug = m.group("slug").lower()
        return ProblemRef(platform=Platform.LEETCODE, external_id=slug, slug=slug)

    # Already a slug.
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", raw):
        return ProblemRef(platform=Platform.LEETCODE, external_id=raw, slug=raw)

    # A human title ("Two Sum") — slugify it.
    slug = slugify(raw)
    if slug:
        return ProblemRef(
            platform=Platform.LEETCODE, external_id=slug, slug=slug, title=raw.strip()
        )

    raise NormalizationError(f"Could not parse a LeetCode problem from {value!r}")


def parse_problem_reference(value: str, platform: str | None = None) -> ProblemRef:
    """Parse any supported problem reference into a canonical `ProblemRef`.

    When `platform` is omitted it is inferred from the URL host or the shape of
    the identifier.
    """
    raw = (value or "").strip()
    if not raw:
        raise NormalizationError("A problem URL or identifier is required")

    if platform:
        platform = platform.strip().lower()
        if platform == Platform.CODEFORCES:
            return parse_codeforces(raw)
        if platform == Platform.LEETCODE:
            return parse_leetcode(raw)
        if platform == Platform.TAKEUFORWARD:
            return parse_takeuforward(raw)
        raise NormalizationError(
            f"Unsupported platform {platform!r}. CP-Forge tracks problems from "
            "LeetCode, Codeforces and takeUforward."
        )

    lowered = raw.lower()
    if "codeforces.com" in lowered:
        return parse_codeforces(raw)
    if "leetcode.com" in lowered:
        return parse_leetcode(raw)
    if _TUF_ID.match(lowered):
        return parse_takeuforward(raw)

    if lowered.startswith(("http://", "https://")):
        host = urlparse(lowered).netloc
        if "takeuforward.org" in host:
            raise NormalizationError(
                "takeUforward URLs do not identify a problem on their own — "
                "their slugs are reused across different problems. Use the "
                "sheet's numeric id (tuf-1234)."
            )
        raise NormalizationError(
            f"{host or 'That site'} is not a supported problem source. "
            "CP-Forge tracks LeetCode and Codeforces problems."
        )

    if _CF_BARE.match(lowered.replace(" ", "")):
        return parse_codeforces(raw)
    return parse_leetcode(raw)


def is_safe_external_url(url: str, allowed_hosts: set[str] | None = None) -> bool:
    """Guard against javascript:/data: URLs and unexpected hosts."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    if allowed_hosts is None:
        return True
    host = parsed.netloc.lower().removeprefix("www.")
    return any(host == h or host.endswith(f".{h}") for h in allowed_hosts)


def normalize_difficulty(value: str | None) -> str:
    if not value:
        return Difficulty.UNKNOWN
    v = value.strip().lower()
    if v in ("easy", "e"):
        return Difficulty.EASY
    if v in ("medium", "med", "m"):
        return Difficulty.MEDIUM
    if v in ("hard", "h"):
        return Difficulty.HARD
    return Difficulty.UNKNOWN


def difficulty_from_rating(rating: int | None) -> str:
    """Map a Codeforces rating onto the easy/medium/hard axis.

    Used only for display consistency; the numeric rating stays authoritative.
    """
    if rating is None:
        return Difficulty.UNKNOWN
    if rating < 1200:
        return Difficulty.EASY
    if rating < 1600:
        return Difficulty.MEDIUM
    return Difficulty.HARD


def rating_bucket(rating: int | None, max_bucket: int = 1700) -> int | None:
    """Rating rounded down to its 100-band, capped at `max_bucket`.

    1250 -> 1200. Everything at or above `max_bucket` lands in it, because the
    top band of a bucketed sheet is a `N+` bucket.

    `max_bucket` is not optional in practice: pass the sheet's own highest
    declared bucket. The 1700 default is only a floor for callers that have no
    sheet in hand — CP-31 now runs to 1900, and using the default there folds
    three bands into one.
    """
    if rating is None:
        return None
    if rating >= max_bucket:
        return max_bucket
    return max(800, (rating // 100) * 100)
