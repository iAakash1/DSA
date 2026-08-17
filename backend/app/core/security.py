"""Authentication.

Two modes:

* ``supabase`` — verify Supabase Auth JWTs. Newer projects sign with RS256/ES256
  and are verified against the project JWKS; legacy projects use an HS256 shared
  secret. Both are supported and auto-detected from the token header.
* ``local`` — single-user development mode with a deterministic user id, so the
  application is fully usable before Supabase credentials exist.

The user id ALWAYS comes from the verified token (or the local-mode constant).
A user id supplied by the client is never trusted.
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
