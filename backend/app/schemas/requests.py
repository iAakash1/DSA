"""Request schemas.

Every write endpoint validates through one of these. SQLAlchemy models are
never accepted or returned directly.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    MistakeType,
    NoteKind,
    ProblemStatus,
    ReviewReason,
    SolutionSource,
)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=128)
    timezone: str | None = Field(None, max_length=64)
    username: str | None = Field(None, max_length=64)


class SettingsUpdate(BaseModel):
    daily_goal: int | None = Field(None, ge=1, le=50)
    weekly_goal: int | None = Field(None, ge=1, le=300)
    max_freezes: int | None = Field(None, ge=0, le=20)
    freeze_cost_xp: int | None = Field(None, ge=0)
    auto_apply_freeze: bool | None = None
    xp_rules_override: dict | None = None
    level_config_override: list | None = None
    ai_daily_insights: bool | None = None
    ai_weekly_reviews: bool | None = None
    ai_contest_analysis: bool | None = None
    ai_recommendations: bool | None = None
    ai_coach: bool | None = None
    ai_daily_request_budget: int | None = Field(None, ge=0, le=1000)
    ai_model_override: str | None = Field(None, max_length=128)


class PlatformAccountRequest(BaseModel):
    platform: str
    username: str = Field(min_length=1, max_length=128)

    @field_validator("platform")
    @classmethod
    def _platform(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("codeforces", "leetcode"):
            raise ValueError("platform must be 'codeforces' or 'leetcode'")
        return v

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        """Accept a pasted profile URL as well as a bare handle."""
        v = v.strip().rstrip("/")
        for marker in ("codeforces.com/profile/", "leetcode.com/u/", "leetcode.com/"):
            if marker in v:
                v = v.split(marker, 1)[1]
                break
        return v.split("/")[0].split("?")[0]


class AddProblemRequest(BaseModel):
    """Paste a URL or an identifier; everything else is optional."""

    reference: str = Field(min_length=1, max_length=512)
    platform: str | None = None
    title: str | None = Field(None, max_length=512)
    difficulty: str | None = None
    rating: int | None = Field(None, gt=0, lt=5000)
    tags: list[str] | None = None
    collection: str | None = None


class RecordSolveRequest(BaseModel):
    solved_at: datetime | None = None
    solution_source: SolutionSource = SolutionSource.INDEPENDENT
    time_spent_seconds: int | None = Field(None, ge=0, le=86_400)
    attempt_count: int = Field(1, ge=1, le=100)
    confidence: int | None = Field(None, ge=1, le=5)
    difficulty_perception: int | None = Field(None, ge=1, le=5)
    approach: str | None = None
    notes: str | None = None
    mistakes: list[MistakeType] = Field(default_factory=list)


class RecordAttemptRequest(BaseModel):
    attempted_at: datetime | None = None
    verdict: str = Field("WRONG_ANSWER", max_length=32)
    time_spent_seconds: int | None = Field(None, ge=0, le=86_400)
    notes: str | None = None
    mistakes: list[MistakeType] = Field(default_factory=list)


class StatusUpdate(BaseModel):
    status: ProblemStatus


class NoteRequest(BaseModel):
    kind: NoteKind = NoteKind.INSIGHT
    content_md: str = Field(min_length=1)


class MistakeRequest(BaseModel):
    mistake_type: MistakeType
    note: str | None = None


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    color: str | None = Field(None, max_length=16)
    icon: str | None = Field(None, max_length=32)


class CollectionItemRequest(BaseModel):
    problem_id: str
    note: str | None = None


class ReviewCompleteRequest(BaseModel):
    outcome: str = "recalled"

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, v: str) -> str:
        if v not in ("recalled", "partial", "forgotten"):
            raise ValueError("outcome must be recalled, partial or forgotten")
        return v


class QueueReviewRequest(BaseModel):
    problem_id: str
    reason: ReviewReason = ReviewReason.MANUAL
    interval_days: int | None = Field(None, ge=1, le=365)


class ContestRequest(BaseModel):
    platform: str
    external_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=512)
    start_time: datetime | None = None
    duration_seconds: int | None = Field(None, ge=0)
    rank: int | None = Field(None, ge=1)
    rating_before: int | None = None
    rating_after: int | None = None
    problems_solved_live: int = Field(0, ge=0)
    penalty: int | None = None
    is_virtual: bool = False
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def _platform(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("codeforces", "leetcode", "codechef"):
            raise ValueError("platform must be codeforces, leetcode or codechef")
        return v


class UpsolveRequest(BaseModel):
    problem_id: str
    status: str = "upsolved"

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ("live", "upsolved", "attempted", "not_attempted"):
            raise ValueError("invalid contest solve status")
        return v


class ImportRequest(BaseModel):
    """Import a sheet from an uploaded payload rather than a file path."""

    payload: dict
    enrich: bool = True


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class TrustedChannelRequest(BaseModel):
    channel_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    weight: float = Field(1.0, ge=0.0, le=3.0)


class ICPCSettingsRequest(BaseModel):
    """Every field optional — this is a partial update."""

    target_date: date | None = None
    team_name: str | None = Field(None, max_length=128)
    weekly_practice_days: int | None = Field(None, ge=1, le=7)
    target_rating: int | None = Field(None, ge=800, le=3500)
    focus_topics: list[str] | None = None
    enabled: bool | None = None


class TopicProgressRequest(BaseModel):
    studied: bool | None = None
    template_reviewed: bool | None = None
    confidence: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=4000)


class TemplateReviewRequest(BaseModel):
    from_memory: bool = False
    seconds_taken: int | None = Field(None, gt=0, le=3600)
    confidence: int | None = Field(None, ge=1, le=5)


class VirtualContestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    problem_ids: list[str] = Field(min_length=1, max_length=15)
    duration_minutes: int = Field(180, gt=0, le=360)


class VirtualContestProblemRequest(BaseModel):
    status: str | None = None
    wrong_attempts: int | None = Field(None, ge=0, le=500)
    solved_at_minute: int | None = Field(None, ge=0, le=360)
