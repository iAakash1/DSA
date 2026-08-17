"""Profile bootstrap and account management."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import AuthenticatedUser, fetch_clerk_profile
from app.models.enums import SYNCABLE_PLATFORMS, Platform
from app.models.gamification import UserStats
from app.models.sheet import Collection
from app.models.user import PlatformAccount, Profile, UserSettings
from app.utils.normalize import slugify
from app.utils.timeutils import get_zone

log = get_logger(__name__)

#: Created for every new user. `is_system` collections cannot be deleted.
SYSTEM_COLLECTIONS: list[tuple[str, str, str, str]] = [
    ("inbox", "Inbox", "Problems you added but have not triaged yet.", "#60a5fa"),
    ("favorites", "Favorites", "Problems worth coming back to.", "#f59e0b"),
    ("revision", "Revision", "Queued for another pass.", "#a78bfa"),
    ("mistakes", "Mistakes", "Problems where something went wrong.", "#f87171"),
]


def ensure_profile(db: Session, auth: AuthenticatedUser) -> Profile:
    """Fetch the caller's profile, creating it (and its dependents) if new.

    `auth.id` is derived from the verified token — under Clerk it is a UUIDv5 of
    the Clerk subject — so lookup by primary key is already the right thing and
    repeated logins resolve to the same row.

    The secondary lookup by `clerk_user_id` exists for the one case the primary
    key cannot cover: a profile that predates Clerk and was later claimed by a
    Clerk user, whose id therefore does not match the derivation.
    """
    profile = db.get(Profile, auth.id)
    if profile is None and auth.clerk_user_id:
        profile = db.scalar(
            select(Profile).where(Profile.clerk_user_id == auth.clerk_user_id)
        )
    if profile is not None:
        # Backfill the mapping the first time a pre-Clerk profile signs in.
        if auth.clerk_user_id and not profile.clerk_user_id:
            profile.clerk_user_id = auth.clerk_user_id
            db.commit()
        return profile

    display_name, email = auth.username, auth.email
    if auth.clerk_user_id:
        # The default Clerk session token carries no name or email; ask the
        # Backend API once, at creation. Failure leaves the token's own values.
        details = fetch_clerk_profile(auth.clerk_user_id)
        if details:
            addresses = {
                a.get("id"): a.get("email_address")
                for a in details.get("email_addresses") or []
            }
            email = addresses.get(details.get("primary_email_address_id")) or email
            display_name = (
                details.get("username")
                or " ".join(
                    part
                    for part in (details.get("first_name"), details.get("last_name"))
                    if part
                ).strip()
                or display_name
            )

    profile = Profile(
        id=auth.id,
        clerk_user_id=auth.clerk_user_id,
        email=email,
        username=auth.username or str(auth.id)[:8],
        display_name=display_name,
        timezone=settings.default_timezone,
    )
    db.add(profile)
    # Flush before adding dependents: they reference profiles.id by column, not
    # by relationship, so SQLAlchemy has no dependency edge to order the
    # INSERTs and would otherwise trip the foreign key.
    db.flush()

    db.add(UserSettings(user_id=auth.id))
    db.add(UserStats(user_id=auth.id))
    for slug, name, description, color in SYSTEM_COLLECTIONS:
        db.add(
            Collection(
                user_id=auth.id,
                slug=slug,
                name=name,
                description=description,
                color=color,
                is_system=True,
            )
        )

    # Bootstrap platform accounts from env when provided — convenience only.
    if settings.codeforces_handle:
        db.add(
            PlatformAccount(
                user_id=auth.id,
                platform=Platform.CODEFORCES,
                username=settings.codeforces_handle,
            )
        )
    if settings.leetcode_username:
        db.add(
            PlatformAccount(
                user_id=auth.id,
                platform=Platform.LEETCODE,
                username=settings.leetcode_username,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        # A concurrent request created it first — that is fine.
        db.rollback()
        existing = db.get(Profile, auth.id)
        if existing is None and auth.clerk_user_id:
            existing = db.scalar(
                select(Profile).where(Profile.clerk_user_id == auth.clerk_user_id)
            )
        if existing is None:
            raise
        return existing

    db.refresh(profile)
    log.info("profile created", user_id=str(auth.id))
    return profile


def get_settings_for(db: Session, user_id: uuid.UUID) -> UserSettings:
    row = db.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_stats_for(db: Session, user_id: uuid.UUID) -> UserStats:
    row = db.get(UserStats, user_id)
    if row is None:
        row = UserStats(user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_profile(db: Session, profile: Profile, **fields) -> Profile:
    if "timezone" in fields and fields["timezone"]:
        tz = fields["timezone"]
        # get_zone falls back silently; compare to catch a genuinely bad value.
        if get_zone(tz).key != tz:
            raise ValidationError(f"Unknown timezone {tz!r}")
    for key, value in fields.items():
        if value is not None and hasattr(profile, key):
            setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


def update_settings(db: Session, user_id: uuid.UUID, **fields) -> UserSettings:
    row = get_settings_for(db, user_id)
    for key, value in fields.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def list_platform_accounts(db: Session, user_id: uuid.UUID) -> list[PlatformAccount]:
    return list(
        db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == user_id)
        ).all()
    )


def upsert_platform_account(
    db: Session, user_id: uuid.UUID, platform: str, username: str
) -> PlatformAccount:
    platform = platform.strip().lower()
    if platform not in SYNCABLE_PLATFORMS:
        raise ValidationError(
            f"{platform!r} is not a supported problem-source platform. "
            "CP-Forge syncs LeetCode and Codeforces."
        )
    username = username.strip()
    if not username:
        raise ValidationError("A username is required")

    account = db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user_id, PlatformAccount.platform == platform
        )
    )
    if account is None:
        account = PlatformAccount(
            user_id=user_id, platform=platform, username=username, connected=True
        )
        db.add(account)
    else:
        if account.username != username:
            # Different account: the old cursor is meaningless.
            account.sync_cursor = None
            account.last_synced_at = None
        account.username = username
        account.connected = True
    db.commit()
    db.refresh(account)
    return account


def disconnect_platform_account(db: Session, user_id: uuid.UUID, platform: str) -> None:
    account = db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user_id, PlatformAccount.platform == platform
        )
    )
    if account is None:
        raise NotFoundError(f"No {platform} account is connected")
    account.connected = False
    db.commit()


def ensure_collection(
    db: Session, user_id: uuid.UUID, name: str, **fields
) -> Collection:
    slug = fields.pop("slug", None) or slugify(name)
    existing = db.scalar(
        select(Collection).where(Collection.user_id == user_id, Collection.slug == slug)
    )
    if existing:
        return existing
    collection = Collection(user_id=user_id, slug=slug, name=name, **fields)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection
