"""Authentication.

Three modes:

* ``clerk`` — the production path. Clerk owns identity; its RS256 session
  tokens are verified against Clerk's JWKS with the issuer pinned to the one
  derived from the publishable key.
* ``supabase`` — legacy Supabase Auth JWTs, kept so existing deployments keep
  working. Supabase remains the *database*; it is not the identity provider.
* ``local`` — single-user development mode with a deterministic user id, so the
  application is usable without any provider configured.

The user id ALWAYS comes from the verified token (or the local-mode constant).
A user id supplied by the client is never trusted.

Clerk subjects are opaque strings (`user_2ab...`), while every row in this
database is keyed by UUID. Rather than rewrite that, the Clerk subject maps to
a UUIDv5 under a fixed namespace: the same Clerk user always yields the same
internal id, with no lookup and no chance of two concurrent first requests
creating two profiles.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

#: Namespace for deriving an internal UUID from a Clerk subject. Fixed forever:
#: changing it would orphan every existing user's data.
CLERK_NAMESPACE = uuid.UUID("6f1c4f2e-9a83-5d1b-8e47-2c0d3b7a9f10")

#: Stable dev identity so local data survives restarts.
LOCAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
LOCAL_USER_EMAIL = "local@cp-forge.dev"
LOCAL_USERNAME = "local"


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    username: str
    claims: dict[str, Any]
    #: Clerk subject, when Clerk issued the token. Stored on the profile so the
    #: mapping is auditable rather than only implied by the UUIDv5 derivation.
    clerk_user_id: str | None = None


def internal_id_for_clerk_subject(subject: str) -> uuid.UUID:
    """Deterministic internal UUID for a Clerk subject."""
    return uuid.uuid5(CLERK_NAMESPACE, subject)


class AuthError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        if not settings.supabase_url:
            raise AuthError("SUPABASE_URL is not configured")
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwk_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwk_client


def decode_supabase_token(token: str) -> dict[str, Any]:
    """Verify a Supabase JWT and return its claims."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("Malformed token") from exc

    alg = header.get("alg", "HS256")

    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthError(
                    "This project issues HS256 tokens but SUPABASE_JWT_SECRET is not set"
                )
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": False},
            )
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[alg],
            audience="authenticated",
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid token") from exc
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        raise AuthError("Could not reach Supabase to verify the session") from exc


def user_from_token(token: str) -> AuthenticatedUser:
    claims = decode_supabase_token(token)
    sub = claims.get("sub")
    if not sub:
        raise AuthError("Token has no subject")

    email = claims.get("email")
    meta = claims.get("user_metadata") or {}
    username = (
        meta.get("username")
        or meta.get("preferred_username")
        or (email.split("@")[0] if email else str(sub)[:8])
    )
    return AuthenticatedUser(
        id=uuid.UUID(str(sub)), email=email, username=username, claims=claims
    )


def local_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=LOCAL_USER_ID,
        email=LOCAL_USER_EMAIL,
        username=LOCAL_USERNAME,
        claims={"sub": str(LOCAL_USER_ID), "mode": "local"},
    )


# ---------------------------------------------------------------------------
# Clerk
# ---------------------------------------------------------------------------

_clerk_jwk_client: PyJWKClient | None = None


def _get_clerk_jwk_client() -> PyJWKClient:
    global _clerk_jwk_client
    if _clerk_jwk_client is None:
        issuer = settings.clerk_issuer_url
        if not issuer:
            raise AuthError("Clerk is not configured on this server")
        _clerk_jwk_client = PyJWKClient(
            f"{issuer}/.well-known/jwks.json", cache_keys=True, lifespan=3600
        )
    return _clerk_jwk_client


def reset_clerk_jwk_client() -> None:
    """Drop the cached JWKS client. Used by tests and after a config change."""
    global _clerk_jwk_client
    _clerk_jwk_client = None


def decode_clerk_token(token: str) -> dict[str, Any]:
    """Verify a Clerk session token and return its claims.

    Signature, expiry and issuer are all checked. The issuer is pinned to the
    value derived from this deployment's publishable key, so a validly-signed
    token from somebody else's Clerk instance is rejected rather than trusted.
    """
    issuer = settings.clerk_issuer_url
    if not issuer:
        raise AuthError("Clerk is not configured on this server")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("Malformed token") from exc

    alg = header.get("alg")
    # Clerk signs with RS256. Naming the algorithm explicitly is what stops an
    # attacker presenting `alg: none` or an HMAC token signed with the public key.
    if alg != "RS256":
        raise AuthError("Unsupported token algorithm")

    try:
        signing_key = _get_clerk_jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
            leeway=5,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("Token was not issued for this application") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid token") from exc
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        raise AuthError("Could not reach Clerk to verify the session") from exc


def _username_from_claims(claims: dict[str, Any], subject: str) -> tuple[str, str | None]:
    """Best-effort display identity from whatever the JWT template includes.

    Clerk's default session token carries only `sub`/`sid`/`iss`/`exp`. Richer
    claims appear when the user configures a JWT template, so both shapes are
    handled and neither is required.
    """
    email = claims.get("email") or claims.get("email_address")
    username = (
        claims.get("username")
        or claims.get("preferred_username")
        or (email.split("@")[0] if email else None)
        or f"user-{subject[-8:]}"
    )
    return username, email


def user_from_clerk_token(token: str) -> AuthenticatedUser:
    claims = decode_clerk_token(token)
    subject = claims.get("sub")
    if not subject:
        raise AuthError("Token has no subject")
    subject = str(subject)

    username, email = _username_from_claims(claims, subject)
    return AuthenticatedUser(
        id=internal_id_for_clerk_subject(subject),
        email=email,
        username=username,
        claims=claims,
        clerk_user_id=subject,
    )


def fetch_clerk_profile(clerk_user_id: str) -> dict[str, Any]:
    """Look up a Clerk user through the Backend API.

    Called once, when a profile is first created, so a user gets a real name and
    email even when the session token carries neither. Failure is not fatal —
    the profile is still created from the token's own claims.
    """
    if not settings.clerk_secret_key:
        return {}
    try:
        response = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=settings.external_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.info("clerk profile lookup unavailable", error=str(exc))
        return {}
