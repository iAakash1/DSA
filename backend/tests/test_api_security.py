"""API-layer authorization.

RLS is defence in depth. The primary control is that the backend derives the
user id from the verified token and never from request input — these tests
assert that directly.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_user
from app.core.security import AuthenticatedUser
from app.main import app
from app.services.solve_service import record_solve


@pytest.fixture
def client():
    return TestClient(app)


def _as(user_id: uuid.UUID):
    """Override the auth dependency to impersonate a verified identity."""
    return lambda: AuthenticatedUser(
        id=user_id, email="x@example.com", username="x", claims={"sub": str(user_id)}
    )


# ---------------------------------------------------------------------------
# Identity cannot be supplied by the client
# ---------------------------------------------------------------------------


def test_user_id_in_query_string_is_ignored(client, db, user, second_user, make_problem):
    """Passing another user's id must not change whose data is returned."""
    problem = make_problem("9001A", rating=1200)
    record_solve(db, user.id, problem.id)

    app.dependency_overrides[get_auth_user] = _as(second_user.id)
    try:
        response = client.get(f"/api/stats?user_id={user.id}")
        assert response.status_code == 200
        # Acting as second_user, who has solved nothing.
        assert response.json()["volume"]["solved_total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_user_id_in_body_is_ignored(client, db, user, second_user, make_problem):
    problem = make_problem("9002A", rating=1200)

    app.dependency_overrides[get_auth_user] = _as(second_user.id)
    try:
        response = client.post(
            f"/api/problems/{problem.id}/solve",
            json={"solution_source": "independent", "user_id": str(user.id)},
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # The solve must belong to second_user, not the injected id.
    from app.services.problem_service import get_user_problem

    assert get_user_problem(db, second_user.id, problem.id).first_solved_at is not None
    assert get_user_problem(db, user.id, problem.id).first_solved_at is None


def test_dashboard_is_scoped_to_the_authenticated_user(client, db, user, second_user, make_problem):
    record_solve(db, user.id, make_problem("9003A", rating=1500).id)

    app.dependency_overrides[get_auth_user] = _as(user.id)
    try:
        mine = client.get("/api/dashboard").json()
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_auth_user] = _as(second_user.id)
    try:
        theirs = client.get("/api/dashboard").json()
    finally:
        app.dependency_overrides.clear()

    assert mine["totals"]["problems_solved"] >= 1
    assert theirs["totals"]["problems_solved"] == 0
    assert theirs["level"]["total_xp"] == 0


def test_cannot_read_another_users_note_by_id(client, db, user, second_user, make_problem):
    """Deleting by a guessed id must 404, not succeed."""
    problem = make_problem("9004A", rating=1000)

    app.dependency_overrides[get_auth_user] = _as(user.id)
    try:
        created = client.post(
            f"/api/problems/{problem.id}/notes",
            json={"kind": "insight", "content_md": "alice private note"},
        ).json()
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[get_auth_user] = _as(second_user.id)
    try:
        response = client.delete(f"/api/problems/{problem.id}/notes/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404, "another user's note must not be deletable"


# ---------------------------------------------------------------------------
# Secrets never leave the server
# ---------------------------------------------------------------------------


def test_health_exposes_capability_flags_not_credentials(client):
    body = client.get("/api/health").json()
    encoded = str(body)

    assert "features" in body
    assert isinstance(body["features"]["ai_configured"], bool)
    for leak in ("gsk_", "service_role", "AIza", "password", "SUPABASE_SERVICE"):
        assert leak not in encoded


def test_ai_status_does_not_leak_the_api_key(client, user):
    app.dependency_overrides[get_auth_user] = _as(user.id)
    try:
        body = client.get("/api/ai/status").json()
    finally:
        app.dependency_overrides.clear()

    assert "gsk_" not in str(body)
    assert "api_key" not in body


def test_settings_response_contains_no_credentials(client, user):
    app.dependency_overrides[get_auth_user] = _as(user.id)
    try:
        body = client.get("/api/me").json()
    finally:
        app.dependency_overrides.clear()

    encoded = str(body)
    for leak in ("gsk_", "AIza", "service_role", "postgresql://", "sb_secret"):
        assert leak not in encoded


# ---------------------------------------------------------------------------
# Supabase auth mode
# ---------------------------------------------------------------------------


def test_supabase_mode_requires_a_bearer_token(monkeypatch):
    """In supabase mode an unauthenticated request must be rejected."""
    from app.core.config import settings
    from app.core.security import AuthError

    monkeypatch.setattr(settings, "auth_mode", "supabase")
    with pytest.raises(AuthError):
        get_auth_user(authorization=None)


def test_malformed_token_is_rejected(monkeypatch):
    from app.core.config import settings
    from app.core.security import AuthError

    monkeypatch.setattr(settings, "auth_mode", "supabase")
    with pytest.raises(AuthError):
        get_auth_user(authorization="Bearer not-a-real-token")
