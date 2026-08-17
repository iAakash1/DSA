"""Problem identity normalization.

If these break, the database silently fills with duplicates and every
statistic becomes wrong — so they are the cheapest high-value tests here.
"""

from __future__ import annotations

import pytest

from app.models.enums import Platform
from app.utils.normalize import (
    NormalizationError,
    difficulty_from_rating,
    is_safe_external_url,
    normalize_codeforces_id,
    parse_problem_reference,
    rating_bucket,
    slugify,
)


@pytest.mark.parametrize(
    "value",
    [
        "1400B",
        "1400/B",
        "1400-B",
        "1400 B",
        "https://codeforces.com/problemset/problem/1400/B",
        "https://codeforces.com/contest/1400/problem/B",
        "https://codeforces.com/contest/1400/problem/b",
    ],
)
def test_codeforces_forms_collapse_to_one_identity(value):
    ref = parse_problem_reference(value)
    assert ref.platform == Platform.CODEFORCES
    assert ref.external_id == "1400B"
    assert ref.canonical_id == "codeforces:1400B"


@pytest.mark.parametrize(
    "value",
    [
        "two-sum",
        "Two Sum",
        "https://leetcode.com/problems/two-sum/",
        "https://leetcode.com/problems/two-sum/description/",
    ],
)
def test_leetcode_forms_collapse_to_one_identity(value):
    ref = parse_problem_reference(value)
    assert ref.platform == Platform.LEETCODE
    assert ref.external_id == "two-sum"


def test_codeforces_index_is_uppercased():
    assert normalize_codeforces_id(1400, "b") == "1400B"
    assert normalize_codeforces_id("1400", "B2") == "1400B2"


def test_unsupported_platform_is_rejected_clearly():
    with pytest.raises(NormalizationError) as exc:
        parse_problem_reference("https://www.codechef.com/problems/FLOW001")
    assert "not a supported problem source" in str(exc.value)


def test_explicit_platform_overrides_inference():
    ref = parse_problem_reference("two-sum", platform="leetcode")
    assert ref.external_id == "two-sum"


def test_empty_reference_is_rejected():
    with pytest.raises(NormalizationError):
        parse_problem_reference("")


def test_rating_bucket_clamps_to_top_bucket():
    assert rating_bucket(800) == 800
    assert rating_bucket(1250) == 1200
    assert rating_bucket(2400) == 1700
    assert rating_bucket(None) is None


def test_rating_bucket_respects_a_sheets_own_ceiling():
    """Regression: CP-31 runs to 1900, not 1700.

    With the default ceiling, ratings of 1700, 1800 and 1900 all collapsed
    into the 1700 section — 93 problems in one band and two empty sections.
    """
    assert rating_bucket(1800, max_bucket=1900) == 1800
    assert rating_bucket(1900, max_bucket=1900) == 1900
    assert rating_bucket(2400, max_bucket=1900) == 1900
    assert rating_bucket(1650, max_bucket=1900) == 1600


def test_difficulty_from_rating_bands():
    assert difficulty_from_rating(900) == "easy"
    assert difficulty_from_rating(1400) == "medium"
    assert difficulty_from_rating(1900) == "hard"


def test_slugify_matches_leetcode_convention():
    assert slugify("Two Sum") == "two-sum"
    assert slugify("Best Time to Buy and Sell Stock II") == "best-time-to-buy-and-sell-stock-ii"


def test_unsafe_urls_are_rejected():
    assert is_safe_external_url("https://youtube.com/watch?v=abc")
    assert not is_safe_external_url("javascript:alert(1)")
    assert not is_safe_external_url("data:text/html,<script>")
    assert not is_safe_external_url("notaurl")


def test_host_allowlist_is_enforced():
    allowed = {"youtube.com"}
    assert is_safe_external_url("https://www.youtube.com/watch?v=x", allowed)
    assert not is_safe_external_url("https://evil.com/watch", allowed)
