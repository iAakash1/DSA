"""API route aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    ai,
    analytics,
    contests,
    gamification,
    health,
    icpc,
    practice,
    problems,
    sheets,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(problems.router)
api_router.include_router(sheets.router)
api_router.include_router(practice.router)
api_router.include_router(analytics.router)
api_router.include_router(gamification.router)
api_router.include_router(contests.router)
api_router.include_router(icpc.router)
api_router.include_router(ai.router)
