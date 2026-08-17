"""Integration tests: canonical problems, imports, isolation, AI fallback."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select

from app.ai.service import AIService
from app.analytics.core import SOLVED_STATUSES
from app.analytics.stats import comfortable_rating, overview
from app.analytics.weakness import detect_weaknesses
from app.core.errors import ValidationError
from app.models.enums import (
    SYNCABLE_PLATFORMS,
    AIInsightType,
    Platform,
    SolutionSource,
)
from app.models.problem import Problem
from app.models.progress import UserProblem
from app.models.sheet import Sheet, SheetProblem
from app.recommendations.engine import generate_recommendations
from app.services.import_service import import_sheet
from app.services.problem_service import get_or_create_problem
from app.services.solve_service import record_solve
from app.services.user_service import upsert_platform_account
from app.utils.normalize import parse_problem_reference

# ---------------------------------------------------------------------------
# Canonical problems
# ---------------------------------------------------------------------------


def test_same_problem_from_different_forms_is_one_row(db):
    """A URL and a bare id must resolve to the same canonical problem."""
    first, created_first = get_or_create_problem(
        db, parse_problem_reference("https://codeforces.com/problemset/problem/1400/B"),
        title="Chess Cheater",
    )
    second, created_second = get_or_create_problem(
        db, parse_problem_reference("1400B"),
    )

    assert created_first is True
    assert created_second is False
    assert first.id == second.id

    count = db.scalar(
        select(func.count(Problem.id)).where(
            Problem.platform == Platform.CODEFORCES, Problem.external_id == "1400B"
        )
    )
    assert count == 1


def test_metadata_merges_without_erasing_known_values(db):
    ref = parse_problem_reference("1401C")
    get_or_create_problem(db, ref, title="Mere Array", rating=1400, tags=["greedy"])
    # A later import that knows less must not blank the rating or the title.
    problem, _ = get_or_create_problem(db, ref, tags=["math"])

    assert problem.title == "Mere Array"
    assert problem.rating == 1400
    assert set(problem.tags) == {"greedy", "math"}


def test_problem_in_two_sheets_stays_one_canonical_row(db, taxonomy):
    payload_a = {
        "sheet": {"slug": "sheet-a", "name": "Sheet A", "kind": "custom"},
        "sections": [{"slug": "s1", "name": "Section 1"}],
        "problems": [{"platform": "codeforces", "external_id": "1402A", "section": "s1"}],
    }
    payload_b = {
        "sheet": {"slug": "sheet-b", "name": "Sheet B", "kind": "custom"},
        "sections": [{"slug": "s1", "name": "Section 1"}],
        "problems": [{"platform": "codeforces", "external_id": "1402A", "section": "s1"}],
    }
    import_sheet(db, payload_a, enrich=False)
    import_sheet(db, payload_b, enrich=False)

    problems = db.scalars(
        select(Problem).where(Problem.external_id == "1402A")
    ).all()
    memberships = db.scalar(
        select(func.count(SheetProblem.id)).join(
            Problem, Problem.id == SheetProblem.problem_id
        ).where(Problem.external_id == "1402A")
    )

    assert len(problems) == 1, "one canonical problem"
    assert memberships == 2, "two sheet memberships"


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_sheet():
    return {
        "sheet": {"slug": "test-sheet", "name": "Test Sheet", "kind": "custom"},
        "sections": [{"slug": "basics", "name": "Basics"}],
        "problems": [
            {"platform": "codeforces", "external_id": "4A", "title": "Watermelon",
             "rating": 800, "section": "basics"},
            {"platform": "leetcode", "external_id": "two-sum", "title": "Two Sum",
             "difficulty": "easy", "section": "basics"},
        ],
    }


def test_import_is_idempotent(db, taxonomy, sample_sheet):
    first = import_sheet(db, sample_sheet, enrich=False)
    second = import_sheet(db, sample_sheet, enrich=False)

    assert first.imported == 2
    assert second.imported == 0, "re-running imports nothing new"
    assert second.updated == 2


def test_import_collapses_duplicates_within_one_file(db, taxonomy):
    payload = {
        "sheet": {"slug": "dupes", "name": "Dupes", "kind": "custom"},
        "sections": [{"slug": "s", "name": "S"}],
        "problems": [
            {"platform": "codeforces", "external_id": "1403A", "section": "s"},
            {"platform": "codeforces", "external_id": "1403A", "section": "s"},
            {"url": "https://codeforces.com/problemset/problem/1403/A", "section": "s"},
        ],
    }
    report = import_sheet(db, payload, enrich=False)

    assert report.imported == 1
    assert report.duplicates_merged == 2


def test_collapsed_duplicates_keep_every_source_row(db, taxonomy):
    """A sheet may reach one problem from several angles; none may vanish.

    Striver A2Z lists `rotate-array` twice — "Left Rotate Array by One" and
    "…by K Places" — and `binary-tree-inorder-traversal` four times. Progress
    has to collapse onto the canonical problem, but the entries are distinct
    exercises, so the sheet must still account for all of them.
    """
    payload = {
        "sheet": {"slug": "angles", "name": "Angles", "kind": "custom"},
        "sections": [{"slug": "arrays", "name": "Arrays"}],
        "problems": [
            {"platform": "leetcode", "external_id": "rotate-array", "section": "arrays",
             "title": "Left Rotate Array by One", "label": "Easy"},
            {"platform": "leetcode", "external_id": "rotate-array", "section": "arrays",
             "title": "Left Rotate Array by K Places", "label": "Easy"},
        ],
    }
    report = import_sheet(db, payload, enrich=False)

    assert report.imported == 1
    assert report.duplicates_merged == 1

    sheet = db.scalar(select(Sheet).where(Sheet.slug == "angles"))
    links = db.scalars(
        select(SheetProblem).where(SheetProblem.sheet_id == sheet.id)
    ).all()
    assert len(links) == 1, "one canonical problem, one membership"
    titles = [entry["title"] for entry in links[0].source_entries]
    assert titles == ["Left Rotate Array by One", "Left Rotate Array by K Places"]


def test_reimport_does_not_duplicate_source_rows(db, taxonomy):
    """Re-running the importer rebuilds the row list instead of appending."""
    payload = {
        "sheet": {"slug": "angles-2", "name": "Angles 2", "kind": "custom"},
        "sections": [{"slug": "arrays", "name": "Arrays"}],
        "problems": [
            {"platform": "leetcode", "external_id": "rotate-array",
             "section": "arrays", "title": "One"},
            {"platform": "leetcode", "external_id": "rotate-array",
             "section": "arrays", "title": "K Places"},
        ],
    }
    import_sheet(db, payload, enrich=False)
    import_sheet(db, payload, enrich=False)

    sheet = db.scalar(select(Sheet).where(Sheet.slug == "angles-2"))
    link = db.scalar(select(SheetProblem).where(SheetProblem.sheet_id == sheet.id))
    assert len(link.source_entries) == 2, "second run must not double the rows"


def test_takeuforward_problems_are_not_syncable(db):
    """The A2Z sheet's own problems have no submission API to sync from."""
    ref = parse_problem_reference("tuf-2807", "takeuforward")
    assert ref.canonical_id == "takeuforward:2807"
    assert Platform.TAKEUFORWARD not in SYNCABLE_PLATFORMS

    with pytest.raises(ValidationError):
        upsert_platform_account(db, uuid.uuid4(), "takeuforward", "someone")


def test_takeuforward_slugs_are_never_treated_as_identity(db, taxonomy):
    """takeUforward serves different problems under one slug.

    `/plus/dsa/problems/cpp` is both "Cpp Basics" and "What are arrays,
    strings?". Keying on the slug would merge them and lose a problem, so the
    numeric sheet id is the identity.
    """
    payload = {
        "sheet": {"slug": "tuf", "name": "TUF", "kind": "a2z"},
        "sections": [{"slug": "basics", "name": "Basics"}],
        "problems": [
            {"platform": "takeuforward", "external_id": "1211", "section": "basics",
             "title": "Cpp Basics", "display_slug": "cpp"},
            {"platform": "takeuforward", "external_id": "2869", "section": "basics",
             "title": "What are arrays, strings?", "display_slug": "cpp"},
        ],
    }
    report = import_sheet(db, payload, enrich=False)

    assert report.imported == 2, "shared slug must not collapse distinct problems"
    assert report.duplicates_merged == 0


def test_premium_leetcode_links_resolve_through_the_login_url(db):
    """The A2Z sheet links premium problems via LeetCode's sign-in page."""
    ref = parse_problem_reference(
        "https://leetcode.com/accounts/login/?next=/problems/find-the-celebrity/"
    )
    assert ref.canonical_id == "leetcode:find-the-celebrity"


def test_import_reports_invalid_rows_without_aborting(db, taxonomy):
    payload = {
        "sheet": {"slug": "partial", "name": "Partial", "kind": "custom"},
        "sections": [{"slug": "s", "name": "S"}],
        "problems": [
            {"platform": "codeforces", "external_id": "1404A", "section": "s"},
            {"platform": "codeforces", "external_id": "1404B", "rating": 99999, "section": "s"},
            {"section": "s"},  # no identifier at all
        ],
    }
    report = import_sheet(db, payload, enrich=False)

    assert report.imported == 1
    assert len(report.errors) == 2, "bad rows reported, good row still imported"


def test_import_requires_a_sheet_block(db):
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        import_sheet(db, {"problems": []}, enrich=False)


# ---------------------------------------------------------------------------
# User isolation
# ---------------------------------------------------------------------------


def test_users_do_not_see_each_others_progress(db, user, second_user, make_problem):
    problem = make_problem("1405A", rating=1200)
    record_solve(db, user.id, problem.id)

    mine = db.scalar(
        select(func.count(UserProblem.id)).where(
            UserProblem.user_id == user.id,
            UserProblem.status.in_(SOLVED_STATUSES),
        )
    )
    theirs = db.scalar(
        select(func.count(UserProblem.id)).where(
            UserProblem.user_id == second_user.id,
            UserProblem.status.in_(SOLVED_STATUSES),
        )
    )

    assert mine == 1
    assert theirs == 0


def test_xp_is_scoped_per_user(db, user, second_user, make_problem):
    from app.gamification.xp import total_xp

    problem = make_problem("1406A", rating=1600)
    record_solve(db, user.id, problem.id)

    assert total_xp(db, user.id) > 0
    assert total_xp(db, second_user.id) == 0


def test_same_problem_solved_by_two_users_stays_one_problem(db, user, second_user, make_problem):
    problem = make_problem("1407A", rating=900)
    record_solve(db, user.id, problem.id)
    record_solve(db, second_user.id, problem.id)

    rows = db.scalars(select(Problem).where(Problem.external_id == "1407A")).all()
    progress = db.scalar(
        select(func.count(UserProblem.id)).where(UserProblem.problem_id == problem.id)
    )
    assert len(rows) == 1
    assert progress == 2


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def test_comfortable_rating_needs_sustained_evidence(db, user, make_problem):
    """One lucky hard solve must not set the comfortable rating."""
    for i in range(4):
        record_solve(db, user.id, make_problem(f"800{i}A", rating=800).id)
    record_solve(db, user.id, make_problem("2000Z", rating=2000).id)

    comfort = comfortable_rating(db, user.id)
    assert comfort == 800, "a single 2000 solve does not make the user a 2000 solver"


def test_synced_solves_do_not_inflate_independence(db, user, make_problem):
    """Platform syncs carry no self-report, so they must be excluded."""
    record_solve(db, user.id, make_problem("1408A", rating=1000).id,
                 solution_source=SolutionSource.UNKNOWN)
    record_solve(db, user.id, make_problem("1408B", rating=1000).id,
                 solution_source=SolutionSource.INDEPENDENT)

    stats = overview(db, user.id, user.timezone)

    assert stats["independence"]["reported_solves"] == 1
    assert stats["independence"]["unreported_solves"] == 1
    assert stats["independence"]["independent_rate"] == 1.0, "1 of 1 *reported* solves"


def test_weakness_engine_stays_quiet_without_data(db, user):
    assert detect_weaknesses(db, user.id, user.timezone) == []


def test_recommendations_never_suggest_solved_problems(db, user, taxonomy, make_problem):
    solved = make_problem("1409A", rating=1200, tags=["dp"])
    make_problem("1409B", rating=1200, tags=["dp"])
    record_solve(db, user.id, solved.id)

    suggestions = generate_recommendations(db, user.id, limit=10)
    suggested_ids = {item["problem_id"] for item in suggestions}

    assert str(solved.id) not in suggested_ids


def test_every_recommendation_carries_a_reason(db, user, taxonomy, make_problem):
    for i in range(4):
        make_problem(f"141{i}A", rating=1100 + i * 100, tags=["graphs"])

    for item in generate_recommendations(db, user.id, limit=5):
        assert item["reason_text"], "recommendations must explain themselves"
        assert item["reason_code"]
        assert item["expected_xp"] > 0


# ---------------------------------------------------------------------------
# AI fallback — the application must never depend on the model
# ---------------------------------------------------------------------------


def test_ai_reports_unavailable_without_a_key(db, user):
    service = AIService(db)
    assert service.available is False
    assert service.status(user.id)["available"] is False


def test_daily_insight_falls_back_to_deterministic_analytics(db, user, make_problem):
    record_solve(db, user.id, make_problem("1411A", rating=1200).id)

    insight = AIService(db).get_or_generate(user.id, AIInsightType.DAILY_INSIGHT)

    assert insight["ai_generated"] is False
    assert insight["status"] == "fallback"
    assert insight["title"], "fallback still produces a usable insight"
    assert insight["structured_output"]["evidence"], "grounded in real metrics"


def test_chat_degrades_gracefully_without_a_key(db, user):
    response = AIService(db).chat(user.id, "Why am I weak at DP?")

    assert response["available"] is False
    assert "unavailable" in response["answer"].lower()
    assert response["tools_used"] == []


def test_ai_tools_are_scoped_to_the_calling_user(db, user, second_user, make_problem):
    """A tool call can never reach another user's data — user_id is not a parameter."""
    from app.ai.tools.analytics_tools import ToolDispatcher

    record_solve(db, user.id, make_problem("1412A", rating=1500).id)

    dispatcher = ToolDispatcher(db, second_user.id, "UTC")
    summary = dispatcher.dispatch("get_user_summary", {"user_id": str(user.id)})

    assert summary["total_xp"] == 0, "the injected user_id must be ignored"


def test_unknown_tool_is_rejected(db, user):
    from app.ai.tools.analytics_tools import ToolDispatcher

    result = ToolDispatcher(db, user.id, "UTC").dispatch("execute_sql", {"q": "DROP TABLE"})
    assert "error" in result


def test_insight_schema_rejects_malformed_output():
    from pydantic import ValidationError as PydanticValidationError

    from app.ai.schemas.insight import AIInsightPayload

    with pytest.raises(PydanticValidationError):
        AIInsightPayload.model_validate_json(json.dumps({"summary": "no title"}))


def test_insight_json_schema_is_strict_mode_compatible():
    """Providers reject $ref/$defs and open objects in strict mode."""
    from app.ai.schemas.insight import AIInsightPayload, json_schema_for

    schema = json_schema_for(AIInsightPayload, "daily")
    encoded = json.dumps(schema)

    assert "$ref" not in encoded
    assert "$defs" not in encoded
    assert schema["schema"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Source provenance, hints and curator videos
# ---------------------------------------------------------------------------


def test_adapter_captures_hints_and_video_links(db, taxonomy):
    """A source that carries hints/videos must not lose them at import."""
    from app.services.import_service import adapt_payload

    payload = adapt_payload(
        [
            {
                "url": "https://codeforces.com/problemset/problem/1500/A",
                "rating": 1500,
                "hints": ["Think about parity", "Now consider prefix sums"],
                "videoUrl": "https://www.youtube.com/watch?v=abc123",
            }
        ],
        slug="cp31", name="CP-31", kind="cp31",
    )
    row = payload["problems"][0]
    assert row["hints"] == ["Think about parity", "Now consider prefix sums"]
    assert row["video_links"] == ["https://www.youtube.com/watch?v=abc123"]

    import_sheet(db, payload, enrich=False)

    problem = db.scalar(select(Problem).where(Problem.external_id == "1500A"))
    assert problem.hints and len(problem.hints) == 2
    assert problem.video_links == ["https://www.youtube.com/watch?v=abc123"]


def test_hints_merge_additively_across_imports(db, taxonomy):
    """A later import must never drop hints an earlier one supplied."""
    from app.services.import_service import adapt_payload

    base = {"url": "https://codeforces.com/problemset/problem/1501/A", "rating": 1500}
    import_sheet(db, adapt_payload([{**base, "hints": ["first"]}],
                                   slug="cp31", name="CP-31", kind="cp31"), enrich=False)
    import_sheet(db, adapt_payload([{**base, "hints": ["second"]}],
                                   slug="cp31", name="CP-31", kind="cp31"), enrich=False)

    problem = db.scalar(select(Problem).where(Problem.external_id == "1501A"))
    assert set(problem.hints) == {"first", "second"}


def test_import_records_source_provenance(db, taxonomy):
    """Which corpus version is loaded must be answerable from the database."""
    from app.models.sheet import Sheet
    from app.services.import_service import (
        PARSER_VERSION,
        adapt_payload,
        source_fingerprint,
    )

    raw = [{"url": "https://codeforces.com/problemset/problem/1502/A", "rating": 900}]
    payload = adapt_payload(raw, slug="prov-sheet", name="Prov", kind="custom")
    import_sheet(db, payload, enrich=False, provenance={
        "source_name": "Test source",
        "source_url": "data/sources/raw/test.json",
        "source_hash": source_fingerprint(raw),
    })

    sheet = db.scalar(select(Sheet).where(Sheet.slug == "prov-sheet"))
    meta = sheet.source_metadata
    assert meta["source_name"] == "Test source"
    assert meta["source_hash"] == source_fingerprint(raw)
    assert meta["parser_version"] == PARSER_VERSION
    assert meta["rows_in_source"] == 1
    assert meta["imported_at"]


def test_source_fingerprint_is_stable_and_order_independent():
    """Key order must not change the hash, or every re-export looks 'changed'."""
    from app.services.import_service import source_fingerprint

    a = {"problems": [{"url": "x", "rating": 800}]}
    b = {"problems": [{"rating": 800, "url": "x"}]}
    assert source_fingerprint(a) == source_fingerprint(b)
    assert source_fingerprint(a) != source_fingerprint({"problems": []})


def test_corpus_is_rebuildable_from_normalized_artifact(db, taxonomy):
    """The normalized artifact alone must reproduce the same memberships."""
    from app.models.sheet import Sheet
    from app.services.import_service import adapt_payload

    raw = [
        {"url": "https://codeforces.com/problemset/problem/1503/A", "rating": 1000},
        {"url": "https://codeforces.com/problemset/problem/1503/B", "rating": 1100},
    ]
    payload = adapt_payload(raw, slug="rebuild", name="Rebuild", kind="cp31")
    import_sheet(db, payload, enrich=False)

    sheet = db.scalar(select(Sheet).where(Sheet.slug == "rebuild"))
    first = db.scalar(
        select(func.count(SheetProblem.id)).where(SheetProblem.sheet_id == sheet.id)
    )

    # Re-import the normalized payload verbatim — counts must be identical.
    import_sheet(db, payload, enrich=False)
    second = db.scalar(
        select(func.count(SheetProblem.id)).where(SheetProblem.sheet_id == sheet.id)
    )
    assert first == second == 2
