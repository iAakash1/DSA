"""Application configuration.

Every externally-tunable value lives here. Nothing in the codebase may read
`os.environ` directly — that keeps configuration auditable and testable.
"""

from __future__ import annotations

import base64
import re

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- app ---------------------------------------------------------------
    app_env: str = "development"
    app_url: str = "http://localhost:5173"
    api_prefix: str = "/api"
    log_level: str = "INFO"

    # -- database ----------------------------------------------------------
    #: PostgreSQL (Supabase) is the only supported runtime database. There is
    #: deliberately no default: an unset DATABASE_URL must fail loudly rather
    #: than silently falling back to a local SQLite file that looks like it
    #: works and then loses the data on deploy.
    #:
    #: SQLite remains supported for the test suite only, which sets
    #: DATABASE_URL explicitly in `tests/conftest.py`.
    database_url: str = ""
    db_echo: bool = False
    #: Escape hatch for offline development without Postgres. Must be set
    #: deliberately; `app_env=production` refuses to honour it.
    allow_sqlite: bool = False

    # -- supabase ----------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    auth_mode: str = "local"

    # -- clerk (identity provider) ----------------------------------------
    #: Server-side only. Never reaches the browser.
    clerk_secret_key: str = ""
    #: Browser-safe. Shared with the frontend via the VITE_ prefix; the backend
    #: reads it only to derive the token issuer.
    vite_clerk_publishable_key: str = ""
    #: Explicit override. Normally derived from the publishable key, which
    #: encodes the Clerk frontend API host.
    clerk_issuer: str = ""

    # -- ai / groq ---------------------------------------------------------
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Groq production models. Llama 3.x is deliberately avoided — it is slated
    # for decommissioning. Override any of these via the environment.
    groq_model: str = "openai/gpt-oss-120b"
    groq_model_fast: str = "openai/gpt-oss-20b"
    groq_model_strong: str = "openai/gpt-oss-120b"
    ai_enabled: bool = True
    ai_requests_per_day: int = 50
    ai_requests_per_minute: int = 5
    ai_timeout_seconds: float = 45.0

    # -- integrations ------------------------------------------------------
    codeforces_handle: str = ""
    leetcode_username: str = ""
    codeforces_api_base: str = "https://codeforces.com/api"
    leetcode_graphql_url: str = "https://leetcode.com/graphql"
    external_timeout_seconds: float = 20.0
    external_max_retries: int = 3

    # -- editorial / video -------------------------------------------------
    youtube_api_key: str = ""
    youtube_trusted_channels: str = ""

    # -- jobs --------------------------------------------------------------
    scheduler_enabled: bool = False
    sync_interval_minutes: int = 180

    # -- defaults for new users -------------------------------------------
    default_timezone: str = "Asia/Kolkata"
    default_daily_goal: int = 2

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def clerk_configured(self) -> bool:
        return bool(self.clerk_secret_key and self.clerk_issuer_url)

    @property
    def clerk_issuer_url(self) -> str:
        """Clerk's token issuer, i.e. the Frontend API origin.

        Clerk publishable keys are `pk_<env>_<base64 of "host$">`, so the issuer
        is derivable from the key the frontend already needs. Deriving it beats
        asking for a second variable that can drift out of sync with the first,
        but `CLERK_ISSUER` still wins when set.
        """
        if self.clerk_issuer:
            return self.clerk_issuer.rstrip("/")
        key = self.vite_clerk_publishable_key.strip()
        if not key:
            return ""
        _, _, encoded = key.partition("_")
        _, _, encoded = encoded.partition("_")
        if not encoded:
            return ""
        try:
            decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        except (ValueError, UnicodeDecodeError):
            return ""
        host = decoded.rstrip("$").strip()
        # Guard against a malformed key turning into a request to some other
        # host: only Clerk-issued domains are accepted.
        if not host or not re.fullmatch(r"[A-Za-z0-9.\-]+", host):
            return ""
        return f"https://{host}"

    @field_validator("auth_mode")
    @classmethod
    def _validate_auth_mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"local", "supabase", "clerk"}:
            raise ValueError("AUTH_MODE must be 'local', 'clerk' or 'supabase'")
        return v

    @field_validator("codeforces_handle", "leetcode_username")
    @classmethod
    def _normalize_handle(cls, v: str) -> str:
        """Accept a profile URL or a bare handle.

        Pasting the profile URL is the natural thing to do, and both platform
        APIs reject it — so normalize instead of failing at sync time.
        """
        v = (v or "").strip().rstrip("/")
        if not v:
            return v
        for marker in ("codeforces.com/profile/", "leetcode.com/u/", "leetcode.com/"):
            if marker in v:
                v = v.split(marker, 1)[1]
                break
        return v.split("/")[0].split("?")[0]

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Normalize the connection URL.

        Two jobs:

        1. Accept the connection string exactly as Supabase presents it
           (`postgresql://…`) and upgrade it to the psycopg 3 driver, so nobody
           has to remember to hand-edit the scheme.
        2. Anchor relative SQLite paths to the repo root — the API runs from
           `backend/`, scripts from the repo root, and Alembic from wherever
           the developer happens to be, so a relative path would otherwise
           resolve to three different files.
        """
        v = v.strip()
        if not v:
            return v

        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]

        prefix = "sqlite:///"
        if not v.startswith(prefix):
            return v

        raw = v[len(prefix) :]
        if raw.startswith(":memory:") or raw.startswith("/"):
            return v

        resolved = (REPO_ROOT / raw.lstrip("./")).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}{resolved}"

    @model_validator(mode="after")
    def _require_a_supported_database(self) -> "Settings":
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is not set.\n"
                "CP-Forge runs on PostgreSQL (Supabase). Copy the connection "
                "string from Supabase > Project Settings > Database and set:\n"
                "  DATABASE_URL=postgresql://postgres.<ref>:<password>"
                "@aws-0-<region>.pooler.supabase.com:5432/postgres\n"
                "For offline development only, set ALLOW_SQLITE=true and "
                "DATABASE_URL=sqlite:///./data/cp_forge.db"
            )
        if self.is_sqlite and not self.allow_sqlite:
            raise ValueError(
                "DATABASE_URL points at SQLite, which is not a supported "
                "runtime database. Set a PostgreSQL URL, or set "
                "ALLOW_SQLITE=true to override for offline development."
            )
        if self.is_sqlite and self.app_env == "production":
            raise ValueError("SQLite cannot be used with APP_ENV=production")
        return self

    # -- derived -----------------------------------------------------------
    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres://"))

    @property
    def ai_configured(self) -> bool:
        """AI is usable only when enabled *and* a key is present."""
        return bool(self.ai_enabled and self.groq_api_key.strip())

    @property
    def youtube_configured(self) -> bool:
        return bool(self.youtube_api_key.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_channel_ids(self) -> list[str]:
        raw = [c.strip() for c in self.youtube_trusted_channels.split(",") if c.strip()]
        return raw or list(DEFAULT_TRUSTED_CHANNELS.values())


# Channel IDs are stable identifiers; handles are not. Users may override these
# entirely via YOUTUBE_TRUSTED_CHANNELS or the settings UI.
DEFAULT_TRUSTED_CHANNELS: dict[str, str] = {
    "takeUforward": "UCJskGeByzRRSvmOyZOz61ig",
    "TLE Eliminators": "UCkVsSTfL8QP93IDPCVOnjOA",
    "Errichto": "UCBr_Fu6q9iHYQCh13jmpbrg",
    "Colin Galen": "UCL7RwUOJqkA1RvPqIWZlWmA",
}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
