"""Clerk authentication.

Clerk owns identity; this database owns persistence. These tests cover the
seam between them: that a token is genuinely verified, that the identity comes
only from the token, and that one Clerk user maps to exactly one internal user
no matter how many times they sign in.

Tokens here are signed with a throwaway RSA key generated in-process and served
through a stubbed JWKS client. No real Clerk secret is involved, and none is
needed — the boundary being tested is the verification logic, not Clerk.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.api.deps import get_auth_user
from app.core import security
from app.core.config import settings
from app.core.security import (
    AuthError,
    internal_id_for_clerk_subject,
    user_from_clerk_token,
)
from app.models.user import Profile
from app.services.user_service import ensure_profile

ISSUER = "https://example-test.clerk.accounts.dev"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def clerk_configured(monkeypatch, signing_key):
    """Point verification at the in-process key instead of Clerk's JWKS."""
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test_not_a_real_key")
    # No Backend API call during tests: profile details come from the token.
    monkeypatch.setattr(security, "fetch_clerk_profile", lambda _: {})
    monkeypatch.setattr(
        "app.services.user_service.fetch_clerk_profile", lambda _: {}
    )

    class _StubKey:
        key = signing_key.public_key()

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, _token):
            return _StubKey()

    monkeypatch.setattr(security, "_get_clerk_jwk_client", lambda: _StubJWKClient())
    yield
    security.reset_clerk_jwk_client()


def make_token(
    signing_key,
    subject: str = "user_2abcdefghijklmno",
    *,
    issuer: str = ISSUER,
    expires_in: int = 3600,
    algorithm: str = "RS256",
    **extra,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "sid": "sess_test",
        **extra,
    }
    key = "not-a-key" if algorithm == "HS256" else signing_key
    return jwt.encode(payload, key, algorithm=algorithm)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def test_valid_token_resolves_an_identity(signing_key):
    auth = user_from_clerk_token(make_token(signing_key))

    assert auth.clerk_user_id == "user_2abcdefghijklmno"
    assert auth.id == internal_id_for_clerk_subject("user_2abcdefghijklmno")


def test_missing_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    with pytest.raises(AuthError):
        get_auth_user(authorization=None)


def test_non_bearer_authorization_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    with pytest.raises(AuthError):
        get_auth_user(authorization="Basic dXNlcjpwYXNz")


def test_malformed_token_is_rejected():
    with pytest.raises(AuthError, match="Malformed"):
        user_from_clerk_token("this.is.not.a.jwt")


def test_expired_token_is_rejected(signing_key):
    token = make_token(signing_key, expires_in=-120)
    with pytest.raises(AuthError, match="expired"):
        user_from_clerk_token(token)


def test_token_from_another_issuer_is_rejected(signing_key):
    """A validly-signed token from somebody else's Clerk instance is not ours."""
    token = make_token(signing_key, issuer="https://attacker.clerk.accounts.dev")
    with pytest.raises(AuthError, match="not issued for this application"):
        user_from_clerk_token(token)


def test_token_signed_with_the_wrong_key_is_rejected(signing_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_token(other)
    with pytest.raises(AuthError, match="Invalid token"):
        user_from_clerk_token(token)


def test_algorithm_confusion_is_rejected(signing_key):
    """`alg: HS256` against an RS256 verifier is the classic JWT forgery."""
    token = make_token(signing_key, algorithm="HS256")
    with pytest.raises(AuthError, match="Unsupported token algorithm"):
        user_from_clerk_token(token)


def test_token_without_a_subject_is_rejected(signing_key):
    now = datetime.now(UTC)
    token = jwt.encode(
        {"iss": ISSUER, "iat": now, "exp": now + timedelta(hours=1)},
        signing_key,
        algorithm="RS256",
    )
    with pytest.raises(AuthError):
        user_from_clerk_token(token)


# ---------------------------------------------------------------------------
# Identity mapping
# ---------------------------------------------------------------------------


def test_first_login_creates_exactly_one_internal_user(db, signing_key):
    subject = f"user_{uuid.uuid4().hex[:16]}"
    auth = user_from_clerk_token(make_token(signing_key, subject))

    profile = ensure_profile(db, auth)

    assert profile.clerk_user_id == subject
    assert profile.id == internal_id_for_clerk_subject(subject)
    assert db.query(Profile).filter(Profile.clerk_user_id == subject).count() == 1


def test_repeated_login_is_idempotent(db, signing_key):
    subject = f"user_{uuid.uuid4().hex[:16]}"

    first = ensure_profile(db, user_from_clerk_token(make_token(signing_key, subject)))
    second = ensure_profile(db, user_from_clerk_token(make_token(signing_key, subject)))
    third = ensure_profile(db, user_from_clerk_token(make_token(signing_key, subject)))

    assert first.id == second.id == third.id
    assert db.query(Profile).filter(Profile.clerk_user_id == subject).count() == 1


def test_two_clerk_users_never_share_an_internal_user(db, signing_key):
    a = ensure_profile(db, user_from_clerk_token(make_token(signing_key, "user_aaa")))
    b = ensure_profile(db, user_from_clerk_token(make_token(signing_key, "user_bbb")))

    assert a.id != b.id
    assert a.clerk_user_id != b.clerk_user_id


def test_existing_data_stays_attached_across_logins(db, signing_key, make_problem):
    """Signing out and back in must not orphan the user's progress."""
    from app.services.solve_service import record_solve

    subject = f"user_{uuid.uuid4().hex[:16]}"
    profile = ensure_profile(db, user_from_clerk_token(make_token(signing_key, subject)))
    record_solve(db, profile.id, make_problem("1234A").id)

    # A new session: new token, same Clerk user.
    again = ensure_profile(db, user_from_clerk_token(make_token(signing_key, subject)))

    from app.models.progress import UserProblem

    solved = (
        db.query(UserProblem).filter(UserProblem.user_id == again.id).count()
    )
    assert again.id == profile.id
    assert solved == 1


def test_a_pre_clerk_profile_is_claimed_rather_than_duplicated(db, signing_key):
    """A profile created before Clerk keeps its id and its data.

    Its UUID predates the derivation, so the primary-key lookup misses; the
    `clerk_user_id` lookup is what stops a second profile being created.
    """
    subject = f"user_{uuid.uuid4().hex[:16]}"
    legacy_id = uuid.uuid4()
    db.add(Profile(id=legacy_id, username="legacy", clerk_user_id=subject))
    db.commit()

    auth = user_from_clerk_token(make_token(signing_key, subject))
    resolved = ensure_profile(db, auth)

    assert resolved.id == legacy_id, "must reuse the existing row, not create one"
    assert db.query(Profile).filter(Profile.clerk_user_id == subject).count() == 1


def test_identity_ignores_client_supplied_user_ids(monkeypatch, signing_key):
    """Only the token decides who the caller is.

    `get_auth_user` takes the Authorization header and nothing else — there is
    no parameter through which a client could nominate a different user.
    """
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    subject = "user_2abcdefghijklmno"
    token = make_token(signing_key, subject)

    auth = get_auth_user(authorization=f"Bearer {token}")

    assert auth.id == internal_id_for_clerk_subject(subject)
    # A claim the client might hope is honoured is not.
    forged = make_token(signing_key, subject, user_id=str(uuid.uuid4()))
    assert get_auth_user(authorization=f"Bearer {forged}").id == auth.id


def test_clerk_subject_derivation_is_stable_forever():
    """A regression here would orphan every existing user's data."""
    assert str(internal_id_for_clerk_subject("user_2abcdefghijklmno")) == str(
        uuid.uuid5(security.CLERK_NAMESPACE, "user_2abcdefghijklmno")
    )
