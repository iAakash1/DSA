"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import AuthenticatedUser, AuthError, local_user, user_from_token
from app.db.session import get_db
from app.models.user import Profile
from app.services.user_service import ensure_profile

DbSession = Annotated[Session, Depends(get_db)]


def get_auth_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """Resolve the caller's identity.

    In `supabase` mode a valid bearer token is mandatory. In `local` mode the
    deterministic dev user is returned so the app runs without Supabase — but a
    token is still honoured if one is presented.
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if settings.auth_mode == "supabase":
        if not token:
            raise AuthError("Sign in to continue")
        return user_from_token(token)

    if token:
        try:
            return user_from_token(token)
        except AuthError:
            # Local mode should not lock the user out over a stale token.
            pass
    return local_user()


AuthUser = Annotated[AuthenticatedUser, Depends(get_auth_user)]


def get_current_profile(db: DbSession, auth: AuthUser) -> Profile:
    """The caller's profile row, created on first sight.

    Every downstream query scopes by `profile.id`, which is derived from the
    verified token — never from request input.
    """
    return ensure_profile(db, auth)


CurrentUser = Annotated[Profile, Depends(get_current_profile)]
