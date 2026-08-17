"""ICPC mode.

The tests that matter here are the negative ones: a readiness engine that
quietly emits a plausible number for a user with no history is worse than no
readiness engine, because the number gets believed.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.errors import NotFoundError, ValidationError
from app.icpc.readiness import MIN_COMPONENTS_FOR_OVERALL, compute_readiness
from app.icpc.roadmap import NODES
from app.icpc.templates import TEMPLATES
from app.services import icpc_service
from app.services.solve_service import record_solve
from app.utils.timeutils import utcnow


# ---------------------------------------------------------------------------
# Readiness refuses to guess
# ---------------------------------------------------------------------------


def test_readiness_is_withheld_for_a_brand_new_user(db, user):
    result = compute_readiness(db, user.id)

    assert result["overall"] is None, "a new user must not receive a score"
    assert result["has_sufficient_data"] is False
    assert result["blocked_reason"]
    assert all(c["score"] is None for c in result["components"])


def test_every_unanswerable_component_says_what_is_missing(db, user):
    result = compute_readiness(db, user.id)

    for component in result["components"]:
        if component["score"] is None:
            assert component["missing"], f"{component['key']} is silent about why"
        # Evidence is reported even when the score cannot be.
        assert component["evidence"]


def test_zero_is_never_used_as_a_stand_in_for_unknown(db, user):
    """The distinction the whole engine exists to preserve."""
    result = compute_readiness(db, user.id)
    scores = [c["score"] for c in result["components"]]

    assert None in scores
    assert 0.0 not in scores, "unknown must not be reported as zero"


def test_contest_readiness_is_not_inferred_from_practice(db, user, make_problem):
    """Solving in practice says nothing about performing under a clock."""
    for i in range(12):
        record_solve(db, user.id, make_problem(f"180{i}A", rating=1500).id)

    result = compute_readiness(db, user.id)
    contest = next(c for c in result["components"] if c["key"] == "contest")

    assert contest["score"] is None
    assert "contest" in contest["missing"].lower()


def test_overall_appears_once_enough_components_have_evidence(db, user, make_problem):
    for i in range(12):
        record_solve(db, user.id, make_problem(f"190{i}B", rating=1400).id)
    icpc_service.record_template_review(db, user.id, "dsu", from_memory=True)
    icpc_service.create_virtual_contest(
        db, user.id, name="Warmup", problem_ids=[make_problem("1999Z").id]
    )

    result = compute_readiness(db, user.id)
    answered = [c for c in result["components"] if c["score"] is not None]

    assert len(answered) >= MIN_COMPONENTS_FOR_OVERALL
    assert result["has_sufficient_data"] is True
    assert result["overall"] is not None
    assert 0.0 <= result["overall"] <= 1.0


def test_missing_components_do_not_drag_the_score_down(db, user, make_problem):
    """Weights are renormalised over what is known, not padded with zeros."""
    for i in range(12):
        record_solve(db, user.id, make_problem(f"171{i}C", rating=1600).id)
    icpc_service.record_template_review(db, user.id, "dijkstra", from_memory=True)
    icpc_service.create_virtual_contest(
        db, user.id, name="Set", problem_ids=[make_problem("1888Q").id]
    )

    result = compute_readiness(db, user.id)
    answered = [c for c in result["components"] if c["score"] is not None]
    weights = result["weights"]
    expected = sum(weights[c["key"]] * c["score"] for c in answered) / sum(
        weights[c["key"]] for c in answered
    )

    assert result["overall"] == pytest.approx(expected, abs=1e-4)


def test_speed_ignores_solves_with_no_recorded_duration(db, user, make_problem):
    """A synced solve has no duration; counting it as instant would fake speed."""
    for i in range(8):
        record_solve(db, user.id, make_problem(f"166{i}D", rating=1400).id)

    result = compute_readiness(db, user.id)
    speed = next(c for c in result["components"] if c["key"] == "speed")

    assert speed["score"] is None
    assert speed["evidence"]["timed_solves"] == 0
    assert "timed" in speed["missing"].lower()


def test_speed_is_measured_once_enough_solves_are_timed(db, user, make_problem):
    for i in range(6):
        record_solve(
            db, user.id, make_problem(f"167{i}E", rating=1400).id,
            time_spent_seconds=15 * 60,
        )

    result = compute_readiness(db, user.id)
    speed = next(c for c in result["components"] if c["key"] == "speed")

    assert speed["score"] is not None
    assert speed["evidence"]["timed_solves"] >= 5
    # 15 minutes is inside the 30-minute target, so this is full marks.
    assert speed["score"] == pytest.approx(1.0)


def test_target_rating_is_flagged_as_assumed_until_chosen(db, user):
    assumed = compute_readiness(db, user.id)
    assert assumed["target_rating_is_default"] is True

    icpc_service.update_settings(db, user.id, target_rating=2100)
    chosen = compute_readiness(db, user.id)

    assert chosen["target_rating_is_default"] is False
    assert chosen["target_rating"] == 2100


# ---------------------------------------------------------------------------
# Countdown
# ---------------------------------------------------------------------------


def test_countdown_is_null_until_a_date_is_set(db, user):
    result = icpc_service.countdown(None, "UTC")
    assert result["days_remaining"] is None
    assert result["message"]


def test_countdown_counts_real_days(db, user):
    target = (utcnow().date()) + timedelta(days=70)
    settings = icpc_service.update_settings(db, user.id, target_date=target)

    result = icpc_service.countdown(settings, "UTC")
    assert result["days_remaining"] == 70
    assert result["weeks_remaining"] == 10
    assert result["is_past"] is False


def test_a_past_contest_date_does_not_go_negative(db, user):
    settings = icpc_service.update_settings(
        db, user.id, target_date=date(2020, 1, 1)
    )
    result = icpc_service.countdown(settings, "UTC")

    assert result["is_past"] is True
    assert result["days_remaining"] == 0


# ---------------------------------------------------------------------------
# Roadmap
# ---------------------------------------------------------------------------


def test_roadmap_marks_blocked_nodes_by_prerequisite(db, user):
    result = icpc_service.roadmap(db, user.id)
    nodes = [n for phase in result["phases"] for n in phase["nodes"]]

    assert len(nodes) == len(NODES)
    flows = next(n for n in nodes if n["key"] == "flows")
    assert flows["state"] == "blocked"
    assert "shortest-path" in flows["unmet_prerequisites"]


def test_self_reported_study_is_kept_apart_from_solve_evidence(db, user):
    icpc_service.set_topic_progress(db, user.id, "dsu", studied=True, confidence=5)
    result = icpc_service.roadmap(db, user.id)
    dsu = next(
        n for phase in result["phases"] for n in phase["nodes"] if n["key"] == "dsu"
    )

    assert dsu["studied"] is True
    assert dsu["self_confidence"] == 5
    # Ticking a box is not evidence of solving anything.
    assert dsu["solved"] == 0
    assert dsu["state"] != "comfortable"


def test_unknown_roadmap_topic_is_rejected(db, user):
    with pytest.raises(ValidationError):
        icpc_service.set_topic_progress(db, user.id, "quantum-computing", studied=True)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_template_library_reports_review_history(db, user):
    library = icpc_service.template_library(db, user.id)
    assert len(library) == len(TEMPLATES)
    assert all(entry["reviews"] == 0 for entry in library)

    icpc_service.record_template_review(db, user.id, "fenwick", from_memory=True)
    library = icpc_service.template_library(db, user.id)
    fenwick = next(e for e in library if e["slug"] == "fenwick")

    assert fenwick["reviews"] == 1
    assert fenwick["typed_from_memory"] is True
    assert fenwick["last_reviewed_at"]


def test_reviewing_a_template_that_does_not_exist_is_a_404(db, user):
    with pytest.raises(NotFoundError):
        icpc_service.record_template_review(db, user.id, "quicksort-but-wrong")


# ---------------------------------------------------------------------------
# Virtual contests
# ---------------------------------------------------------------------------


def test_virtual_contest_scores_icpc_penalty(db, user, make_problem):
    a, b = make_problem("1500A"), make_problem("1500B")
    contest = icpc_service.create_virtual_contest(
        db, user.id, name="Regional warmup", problem_ids=[a.id, b.id]
    )

    icpc_service.update_contest_problem(
        db, user.id, contest.id, a.id, status="solved", solved_at_minute=25
    )
    icpc_service.update_contest_problem(
        db, user.id, contest.id, b.id, status="solved",
        solved_at_minute=90, wrong_attempts=2,
    )
    result = icpc_service.finish_virtual_contest(db, user.id, contest.id)

    # 25 + (90 + 2 * 20) = 155
    assert result["penalty_minutes"] == 155
    assert result["solved_count"] == 2
    assert result["status"] == "finished"


def test_unsolved_contest_problems_become_the_upsolve_queue(db, user, make_problem):
    a, b = make_problem("1600A"), make_problem("1600B")
    contest = icpc_service.create_virtual_contest(
        db, user.id, name="Mock", problem_ids=[a.id, b.id]
    )
    icpc_service.update_contest_problem(
        db, user.id, contest.id, a.id, status="solved", solved_at_minute=40
    )
    icpc_service.update_contest_problem(
        db, user.id, contest.id, b.id, status="attempted", wrong_attempts=3
    )
    icpc_service.finish_virtual_contest(db, user.id, contest.id)

    queue = icpc_service.unsolved_from_contests(db, user.id)
    assert [row["problem_id"] for row in queue] == [str(b.id)]
    assert queue[0]["wrong_attempts"] == 3


def test_a_contest_cannot_list_the_same_problem_twice(db, user, make_problem):
    p = make_problem("1700A")
    with pytest.raises(ValidationError):
        icpc_service.create_virtual_contest(
            db, user.id, name="Dupe", problem_ids=[p.id, p.id]
        )


def test_solve_time_must_fall_inside_the_contest(db, user, make_problem):
    p = make_problem("1700B")
    contest = icpc_service.create_virtual_contest(
        db, user.id, name="Short", problem_ids=[p.id], duration_minutes=60
    )
    with pytest.raises(ValidationError):
        icpc_service.update_contest_problem(
            db, user.id, contest.id, p.id, status="solved", solved_at_minute=90
        )


def test_contests_are_scoped_to_their_owner(db, user, second_user, make_problem):
    p = make_problem("1700C")
    contest = icpc_service.create_virtual_contest(
        db, user.id, name="Mine", problem_ids=[p.id]
    )

    assert icpc_service.list_virtual_contests(db, second_user.id) == []
    with pytest.raises(NotFoundError):
        icpc_service.update_contest_problem(
            db, second_user.id, contest.id, p.id, status="solved"
        )


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def test_snapshot_records_insufficient_data_honestly(db, user):
    result = icpc_service.snapshot_readiness(db, user.id)
    assert result["has_sufficient_data"] is False

    trend = icpc_service.readiness_trend(db, user.id)
    assert len(trend) == 1
    assert trend[0]["overall"] is None
    assert trend[0]["has_sufficient_data"] is False
