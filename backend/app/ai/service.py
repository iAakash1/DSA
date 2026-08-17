"""AI orchestration.

Responsibilities, in order of importance:

1. **Never break the app.** Every failure path returns a deterministic fallback
   built from the analytics engine. AI is a layer on top, not a dependency.
2. **Never spend a token twice for the same answer.** Insights are cached
   against a hash of the metrics that produced them.
3. **Never trust raw model output.** Responses are validated against Pydantic
   schemas before they touch the database or the UI.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.context.builder import AIContextBuilder, snapshot_hash
from app.ai.prompts.library import get_prompt
from app.ai.providers.base import AIProvider, ProviderError, ProviderResponse
from app.ai.providers.groq import GroqProvider
from app.ai.schemas.insight import (
    AIInsightPayload,
    StudyPlanPayload,
    WeaknessPayload,
    json_schema_for,
)
from app.ai.tools.analytics_tools import TOOL_SCHEMAS, ToolDispatcher
from app.core.config import settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger
from app.models.ai import AIConversation, AIInsight, AIMessage, AIUsage
from app.models.enums import AIInsightType, Confidence, InsightStatus
from app.models.user import Profile, UserSettings
from app.utils.timeutils import utcnow

log = get_logger(__name__)

#: How long each insight type stays fresh.
TTL_HOURS = {
    AIInsightType.DAILY_INSIGHT: 20,
    AIInsightType.WEEKLY_REVIEW: 24 * 7,
    AIInsightType.MONTHLY_REVIEW: 24 * 30,
    AIInsightType.WEAKNESS_ANALYSIS: 24,
    AIInsightType.PROGRESS_ANALYSIS: 24,
    AIInsightType.MISTAKE_ANALYSIS: 24,
    AIInsightType.STUDY_PLAN: 24 * 7,
    AIInsightType.CONTEST_ANALYSIS: 24 * 365,
}

#: Which structured schema each insight type must validate against.
SCHEMAS: dict[str, type[BaseModel]] = {
    AIInsightType.WEAKNESS_ANALYSIS: WeaknessPayload,
    AIInsightType.STUDY_PLAN: StudyPlanPayload,
}

#: Heavier reasoning gets the strong model; short summaries get the fast one.
STRONG_TYPES = {
    AIInsightType.WEEKLY_REVIEW,
    AIInsightType.MONTHLY_REVIEW,
    AIInsightType.WEAKNESS_ANALYSIS,
    AIInsightType.CONTEST_ANALYSIS,
    AIInsightType.STUDY_PLAN,
}

MAX_TOOL_ROUNDS = 4


class AIService:
    def __init__(self, db: Session, provider: AIProvider | None = None) -> None:
        self.db = db
        self.provider = provider or GroqProvider()

    # -- availability ------------------------------------------------------

    @property
    def available(self) -> bool:
        return settings.ai_configured and self.provider.configured

    def status(self, user_id: uuid.UUID) -> dict[str, Any]:
        config = self.db.get(UserSettings, user_id)
        used = self._requests_today(user_id)
        budget = config.ai_daily_request_budget if config else settings.ai_requests_per_day
        return {
            "available": self.available,
            "provider": self.provider.name,
            "model": self._model_for(AIInsightType.DAILY_INSIGHT, user_id),
            "requests_today": used,
            "daily_budget": budget,
            "remaining": max(0, budget - used),
            "reason": None if self.available else "No Groq API key is configured.",
        }

    def _model_for(self, insight_type: str, user_id: uuid.UUID) -> str:
        config = self.db.get(UserSettings, user_id)
        if config and config.ai_model_override:
            return config.ai_model_override
        if insight_type in STRONG_TYPES:
            return settings.groq_model_strong
        return settings.groq_model

    # -- rate limiting -----------------------------------------------------

    def _requests_today(self, user_id: uuid.UUID) -> int:
        since = utcnow() - timedelta(days=1)
        return int(
            self.db.scalar(
                select(func.count(AIUsage.id)).where(
                    AIUsage.user_id == user_id, AIUsage.created_at >= since
                )
            )
            or 0
        )

    def _check_budget(self, user_id: uuid.UUID) -> None:
        config = self.db.get(UserSettings, user_id)
        budget = config.ai_daily_request_budget if config else settings.ai_requests_per_day
        if budget and self._requests_today(user_id) >= budget:
            raise RateLimitError(
                f"You have used your {budget} AI requests for today. "
                "Deterministic analytics remain fully available."
            )

    def _record_usage(
        self,
        user_id: uuid.UUID,
        endpoint: str,
        model: str,
        response: ProviderResponse | None,
        success: bool,
        error: str | None = None,
    ) -> None:
        self.db.add(
            AIUsage(
                user_id=user_id,
                endpoint=endpoint,
                model=model,
                input_tokens=response.input_tokens if response else 0,
                output_tokens=response.output_tokens if response else 0,
                latency_ms=response.latency_ms if response else 0,
                success=success,
                error=error,
            )
        )
        self.db.commit()

    # -- insights ----------------------------------------------------------

    def get_or_generate(
        self,
        user_id: uuid.UUID,
        insight_type: str,
        *,
        force: bool = False,
        context_override: dict[str, Any] | None = None,
        subject_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Return a cached insight, or generate one. Never raises for AI errors."""
        context = context_override or AIContextBuilder(self.db, user_id).for_type(
            insight_type
        )
        digest = snapshot_hash(context)

        if not force:
            cached = self._cached(user_id, insight_type, digest, subject_id)
            if cached is not None:
                return self._serialize(cached, cached_hit=True)

        if not self.available:
            return self._fallback(
                user_id,
                insight_type,
                context,
                "AI Coach is unavailable because no Groq API key is configured.",
            )

        try:
            self._check_budget(user_id)
        except RateLimitError as exc:
            return self._fallback(user_id, insight_type, context, exc.message)

        try:
            insight = self._generate(user_id, insight_type, context, digest, subject_id)
        except ProviderError as exc:
            log.warning("ai generation failed", type=insight_type, error=exc.message)
            self._record_usage(
                user_id,
                insight_type,
                self._model_for(insight_type, user_id),
                None,
                success=False,
                error=exc.message,
            )
            # A stale insight beats no insight.
            stale = self._latest(user_id, insight_type, subject_id)
            if stale is not None:
                return {
                    **self._serialize(stale, cached_hit=True),
                    "stale": True,
                    "message": f"Showing your last insight — {exc.message}",
                }
            return self._fallback(
                user_id, insight_type, context, f"AI unavailable: {exc.message}"
            )

        return self._serialize(insight, cached_hit=False)

    def _generate(
        self,
        user_id: uuid.UUID,
        insight_type: str,
        context: dict[str, Any],
        digest: str,
        subject_id: uuid.UUID | None,
    ) -> AIInsight:
        prompt = get_prompt(insight_type)
        schema_model = SCHEMAS.get(insight_type, AIInsightPayload)
        model = self._model_for(insight_type, user_id)

        messages = [
            {"role": "system", "content": prompt.system},
            {
                "role": "user",
                "content": (
                    f"{prompt.instruction}\n\n"
                    "CONTEXT (the only facts you may cite):\n"
                    f"{json.dumps(context, indent=2, default=str)}"
                ),
            },
        ]

        response = self.provider.complete(
            messages,
            model=model,
            temperature=0.3,
            json_schema=json_schema_for(schema_model, insight_type),
        )
        payload = self._validate(response.content, schema_model, messages, model)

        self._record_usage(user_id, insight_type, model, response, success=True)

        insight = AIInsight(
            user_id=user_id,
            type=insight_type,
            title=_title_of(payload, insight_type),
            summary=_summary_of(payload),
            content=response.content,
            structured_output=payload.model_dump(mode="json"),
            context_snapshot=context,
            model=response.model or model,
            prompt_version=prompt.version,
            data_snapshot_hash=digest,
            confidence=getattr(payload, "confidence", Confidence.MEDIUM),
            status=InsightStatus.OK,
            generated_at=utcnow(),
            expires_at=utcnow() + timedelta(hours=TTL_HOURS.get(insight_type, 24)),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            subject_id=subject_id,
        )
        self.db.add(insight)
        self.db.commit()
        self.db.refresh(insight)
        return insight

    def _validate(
        self,
        content: str,
        schema_model: type[BaseModel],
        messages: list[dict[str, Any]],
        model: str,
    ) -> BaseModel:
        """Parse and validate, retrying once with the error fed back."""
        try:
            return schema_model.model_validate_json(content)
        except (PydanticValidationError, ValueError) as first_error:
            log.info("ai output failed validation, retrying once")
            repair = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "That response did not match the required schema:\n"
                        f"{first_error}\n\n"
                        "Return ONLY valid JSON matching the schema. Do not add "
                        "commentary or invent any values."
                    ),
                },
            ]
            response = self.provider.complete(
                repair,
                model=model,
                temperature=0.0,
                json_schema=json_schema_for(schema_model, "repair"),
            )
            try:
                return schema_model.model_validate_json(response.content)
            except (PydanticValidationError, ValueError) as second_error:
                raise ProviderError(
                    f"Model returned invalid structured output: {second_error}"
                ) from second_error

    # -- caching -----------------------------------------------------------

    def _cached(
        self,
        user_id: uuid.UUID,
        insight_type: str,
        digest: str,
        subject_id: uuid.UUID | None,
    ) -> AIInsight | None:
        query = select(AIInsight).where(
            AIInsight.user_id == user_id,
            AIInsight.type == insight_type,
            AIInsight.data_snapshot_hash == digest,
            AIInsight.status == InsightStatus.OK,
        )
        if subject_id is not None:
            query = query.where(AIInsight.subject_id == subject_id)
        insight = self.db.scalar(query.order_by(AIInsight.generated_at.desc()).limit(1))
        if insight is None:
            return None
        if insight.expires_at and insight.expires_at < utcnow():
            return None
        return insight

    def _latest(
        self, user_id: uuid.UUID, insight_type: str, subject_id: uuid.UUID | None = None
    ) -> AIInsight | None:
        query = select(AIInsight).where(
            AIInsight.user_id == user_id,
            AIInsight.type == insight_type,
            AIInsight.status == InsightStatus.OK,
        )
        if subject_id is not None:
            query = query.where(AIInsight.subject_id == subject_id)
        return self.db.scalar(query.order_by(AIInsight.generated_at.desc()).limit(1))

    # -- fallback ----------------------------------------------------------

    def _fallback(
        self,
        user_id: uuid.UUID,
        insight_type: str,
        context: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        """Deterministic insight built without a model.

        This is what makes AI genuinely optional: the same observation and
        action, phrased from the analytics rather than generated.
        """
        weak = (context.get("weak_topics") or [None])[0]
        practice = context.get("practice") or {}
        difficulty = context.get("difficulty") or {}

        if weak:
            title = f"{weak['topic']} is your weakest area"
            summary = (
                f"{weak['topic']} sits at {weak['mastery_percent']}% mastery "
                f"({weak['root_cause'].lower()})."
            )
            evidence = [
                {"metric": "mastery_percent", "value": str(weak["mastery_percent"])},
                *[
                    {"metric": "signal", "value": item}
                    for item in (weak.get("evidence") or [])[:3]
                ],
            ]
            recommendations = [
                {
                    "action": f"Practise {weak['topic']} at {weak.get('recommended_difficulty') or 'your current band'}",
                    "reason": weak["root_cause"],
                }
            ]
        else:
            solved = practice.get("problems_solved_last_30_days", 0)
            title = "Your practice summary"
            summary = (
                f"You solved {solved} problems in the last 30 days. "
                "Not enough topic data yet to identify a weakness."
            )
            evidence = [
                {
                    "metric": "problems_solved_last_30_days",
                    "value": str(solved),
                }
            ]
            recommendations = [
                {
                    "action": "Record solve time and confidence when you solve",
                    "reason": "Analytics need self-reported data to find weaknesses.",
                }
            ]

        return {
            "type": insight_type,
            "title": title,
            "summary": summary,
            "confidence": Confidence.MEDIUM if weak else Confidence.INSUFFICIENT_DATA,
            "structured_output": {
                "title": title,
                "summary": summary,
                "diagnosis": "",
                "evidence": evidence,
                "recommendations": recommendations,
                "metrics_used": [e["metric"] for e in evidence],
            },
            "context_snapshot": context,
            "status": InsightStatus.FALLBACK,
            "ai_generated": False,
            "message": message,
            "generated_at": utcnow().isoformat(),
            "difficulty_note": difficulty.get("comfortable_rating"),
        }

    def _serialize(self, insight: AIInsight, cached_hit: bool) -> dict[str, Any]:
        return {
            "id": str(insight.id),
            "type": insight.type,
            "title": insight.title,
            "summary": insight.summary,
            "confidence": insight.confidence,
            "structured_output": insight.structured_output,
            "context_snapshot": insight.context_snapshot,
            "status": insight.status,
            "ai_generated": True,
            "model": insight.model,
            "prompt_version": insight.prompt_version,
            "generated_at": insight.generated_at.isoformat(),
            "expires_at": insight.expires_at.isoformat() if insight.expires_at else None,
            "cached": cached_hit,
            "tokens": {
                "input": insight.input_tokens,
                "output": insight.output_tokens,
            },
            "latency_ms": insight.latency_ms,
        }

    # -- chat --------------------------------------------------------------

    def chat(
        self, user_id: uuid.UUID, message: str, conversation_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """Answer a question using tool-grounded retrieval of the user's data."""
        if not self.available:
            return {
                "available": False,
                "answer": (
                    "AI Coach is unavailable because no Groq API key is configured. "
                    "Your analytics, recommendations and review queue all still work."
                ),
                "tools_used": [],
            }

        self._check_budget(user_id)

        conversation = self._conversation(user_id, conversation_id)
        profile = self.db.get(Profile, user_id)
        tz = profile.timezone if profile else "UTC"
        dispatcher = ToolDispatcher(self.db, user_id, tz)
        prompt = get_prompt(AIInsightType.COACH_CHAT)
        model = self._model_for(AIInsightType.COACH_CHAT, user_id)

        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt.system}]
        messages.extend(self._history(conversation))
        messages.append({"role": "user", "content": message})

        response: ProviderResponse | None = None
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = self.provider.complete(
                    messages, model=model, temperature=0.4, tools=TOOL_SCHEMAS
                )
                if not response.wants_tools:
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or None,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments),
                                },
                            }
                            for call in response.tool_calls
                        ],
                    }
                )
                for call in response.tool_calls:
                    result = dispatcher.dispatch(call.name, call.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(result, default=str)[:6000],
                        }
                    )
        except ProviderError as exc:
            self._record_usage(
                user_id, "coach_chat", model, response, success=False, error=exc.message
            )
            return {
                "available": False,
                "answer": f"AI Coach is temporarily unavailable ({exc.message}).",
                "tools_used": dispatcher.called,
                "conversation_id": str(conversation.id),
            }

        answer = (response.content if response else "") or (
            "I could not produce an answer from your data."
        )
        self._record_usage(user_id, "coach_chat", model, response, success=True)

        self.db.add(
            AIMessage(
                conversation_id=conversation.id,
                user_id=user_id,
                role="user",
                content=message,
            )
        )
        self.db.add(
            AIMessage(
                conversation_id=conversation.id,
                user_id=user_id,
                role="assistant",
                content=answer,
                tool_calls=dispatcher.called,
                model=model,
                tokens=(response.output_tokens if response else 0),
            )
        )
        if conversation.title == "New conversation":
            conversation.title = message[:60]
        self.db.commit()

        return {
            "available": True,
            "answer": answer,
            "tools_used": dispatcher.called,
            "conversation_id": str(conversation.id),
            "model": model,
        }

    def _conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID | None
    ) -> AIConversation:
        if conversation_id is not None:
            existing = self.db.scalar(
                select(AIConversation).where(
                    AIConversation.id == conversation_id,
                    AIConversation.user_id == user_id,
                )
            )
            if existing is not None:
                return existing

        conversation = AIConversation(user_id=user_id)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def _history(self, conversation: AIConversation, limit: int = 8) -> list[dict[str, str]]:
        """Recent turns only — context stays bounded regardless of thread age."""
        rows = self.db.scalars(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation.id)
            .order_by(AIMessage.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {"role": row.role, "content": row.content} for row in reversed(list(rows))
        ]

    # -- usage -------------------------------------------------------------

    def usage(self, user_id: uuid.UUID) -> dict[str, Any]:
        day_ago = utcnow() - timedelta(days=1)
        month_ago = utcnow() - timedelta(days=30)

        def aggregate(since):
            row = self.db.execute(
                select(
                    func.count(AIUsage.id),
                    func.coalesce(func.sum(AIUsage.input_tokens), 0),
                    func.coalesce(func.sum(AIUsage.output_tokens), 0),
                    func.coalesce(func.avg(AIUsage.latency_ms), 0),
                ).where(AIUsage.user_id == user_id, AIUsage.created_at >= since)
            ).one()
            return {
                "requests": int(row[0]),
                "input_tokens": int(row[1]),
                "output_tokens": int(row[2]),
                "average_latency_ms": int(row[3]),
            }

        config = self.db.get(UserSettings, user_id)
        budget = config.ai_daily_request_budget if config else settings.ai_requests_per_day
        today = aggregate(day_ago)

        failures = int(
            self.db.scalar(
                select(func.count(AIUsage.id)).where(
                    AIUsage.user_id == user_id,
                    AIUsage.created_at >= month_ago,
                    AIUsage.success.is_(False),
                )
            )
            or 0
        )

        return {
            "available": self.available,
            "model": self._model_for(AIInsightType.DAILY_INSIGHT, user_id),
            "today": today,
            "last_30_days": aggregate(month_ago),
            "daily_budget": budget,
            "remaining_today": max(0, budget - today["requests"]),
            "failures_last_30_days": failures,
        }


def _title_of(payload: BaseModel, insight_type: str) -> str:
    title = getattr(payload, "title", None)
    if title:
        return str(title)[:500]
    return insight_type.replace("_", " ").title()


def _summary_of(payload: BaseModel) -> str:
    return str(getattr(payload, "summary", ""))[:2000]
