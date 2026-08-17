"""CP-Forge API entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.db.bootstrap import verify_or_warn
from app.jobs.scheduler import shutdown_scheduler, start_scheduler

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info(
        "cp-forge starting",
        env=settings.app_env,
        auth_mode=settings.auth_mode,
        database="postgresql" if settings.is_postgres else "sqlite",
        ai_configured=settings.ai_configured,
    )
    if settings.is_sqlite and settings.app_env == "production":
        log.warning(
            "running production on SQLite — set DATABASE_URL to your Supabase "
            "Postgres connection string"
        )
    # Schema is owned by migrations. Verify, never create.
    verify_or_warn()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        log.info("cp-forge stopped")


app = FastAPI(
    title="CP-Forge",
    description="A competitive programming preparation OS.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": "CP-Forge", "docs": "/docs", "api": settings.api_prefix}
