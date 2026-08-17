"""Controlled tools the AI Coach may call.

The model gets a fixed, schema-validated menu of read-only analytics functions.
It never receives database access, never receives SQL, and every call is scoped
to the authenticated user by the dispatcher — the model cannot name a different
user because `user_id` is not a parameter of any tool.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.logging import get_logger

log = get_logger(__name__)

#: Results are truncated so one tool call cannot blow the context window.
MAX_ITEMS = 12


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _tool(
        "get_user_summary",
        "Overall snapshot: streak, level, XP, problems solved, reviews due.",
        {},
    ),
    _tool(
        "get_practice_stats",
        "Volume, success rate, solve time and independent-solve rates, "
        "including the previous period for comparison.",
        {},
    ),
    _tool(
        "get_difficulty_progression",
        "Average/median/highest solved rating, the comfortable rating band, "
        "and month-by-month progression.",
        {},
    ),
    _tool(
        "get_topic_stats",
        "Mastery, success rate, solve time and recency per topic. "
        "Pass a topic name to narrow to one topic.",
        {"topic": {"type": "string", "description": "Optional topic name filter"}},
    ),
    _tool(
        "get_pattern_stats",
        "The same metrics per solving pattern (Sliding Window, Dijkstra, ...).",
        {"pattern": {"type": "string", "description": "Optional pattern name filter"}},
    ),
    _tool(
        "get_weak_topics",
        "Ranked weaknesses with computed evidence and root cause "
        "(thin exposure vs repeated struggle).",
        {},
    ),
    _tool(
        "get_mistake_distribution",
        "Recorded mistakes by type, split into implementation vs conceptual.",
        {},
    ),
    _tool(
        "get_recommendations",
        "Problems the deterministic engine currently recommends, with reasons. "
        "Use this to answer 'what should I solve'. Never invent problems.",
        {"limit": {"type": "integer", "description": "How many, max 10"}},
    ),
    _tool(
        "get_sheet_progress",
        "Completion for CP-31 and Striver A2Z, including per-section progress.",
        {"sheet": {"type": "string", "description": "Optional sheet slug: cp31 or striver-a2z"}},
    ),
    _tool(
        "get_recent_activity",
        "Recently solved problems with dates, ratings and solution sources.",
        {"limit": {"type": "integer", "description": "How many, max 12"}},
    ),
    _tool(
        "get_review_queue",
        "Problems currently due for spaced review, and why each was queued.",
        {},
    ),
    _tool(
        "get_contest_history",
        "Recent contests with rank, rating change, live solves and upsolves.",
        {"limit": {"type": "integer", "description": "How many, max 10"}},
    ),
]


class ToolDispatcher:
    """Executes tool calls for exactly one user."""

    def __init__(self, db: Session, user_id: uuid.UUID, tz: str = "UTC") -> None:
        self.db = db
        self.user_id = user_id
        self.tz = tz
        self._calls: list[str] = []

    @property
    def called(self) -> list[str]:
        return list(self._calls)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        handler: Callable | None = getattr(self, f"_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool {name!r}"}

        self._calls.append(name)
        try:
            return handler(**_sanitize(arguments))
        except TypeError as exc:
            return {"error": f"Invalid arguments for {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - a tool failure must not kill the chat
            log.warning("ai tool failed", tool=name, error=str(exc))
            return {"error": f"{name} is unavailable right now"}

    # -- tools -------------------------------------------------------------

    def _builder(self):
        from app.ai.context.builder import AIContextBuilder

        return AIContextBuilder(self.db, self.user_id)

    def _get_user_summary(self) -> dict:
        return self._builder().user_summary()

    def _get_practice_stats(self) -> dict:
        return self._builder().practice()

    def _get_difficulty_progression(self) -> dict:
        from app.analytics.stats import difficulty_progression

        return {
            **self._builder().difficulty(),
            "monthly": difficulty_progression(self.db, self.user_id, months=6)["monthly"],
        }

    def _get_topic_stats(self, topic: str | None = None) -> Any:
        from app.analytics.mastery import topic_mastery

        stats = topic_mastery(self.db, self.user_id, self.tz)
        if topic:
            needle = topic.strip().lower()
            stats = [s for s in stats if needle in s.name.lower() or needle in s.slug]
            if not stats:
                return {"error": f"No recorded data for topic {topic!r}"}
        return [_topic_row(s) for s in stats[:MAX_ITEMS]]

    def _get_pattern_stats(self, pattern: str | None = None) -> Any:
        from app.analytics.mastery import pattern_mastery

        stats = pattern_mastery(self.db, self.user_id, self.tz)
        if pattern:
            needle = pattern.strip().lower()
            stats = [s for s in stats if needle in s.name.lower() or needle in s.slug]
            if not stats:
                return {"error": f"No recorded data for pattern {pattern!r}"}
        return [_topic_row(s) for s in stats[:MAX_ITEMS]]

    def _get_weak_topics(self) -> list[dict]:
        return self._builder().weak_topics(limit=6)

    def _get_mistake_distribution(self) -> dict:
        return self._builder().mistakes()

    def _get_recommendations(self, limit: int = 5) -> list[dict]:
        return self._builder().recommended_problems(limit=min(int(limit or 5), 10))

    def _get_sheet_progress(self, sheet: str | None = None) -> Any:
        from app.services.sheet_service import sheet_detail

        if sheet:
            try:
                detail = sheet_detail(self.db, self.user_id, sheet)
            except Exception:  # noqa: BLE001
                return {"error": f"Sheet {sheet!r} has not been imported"}
            return {
                "name": detail["name"],
                "percent": detail["progress"]["percent"],
                "completed": detail["progress"]["completed"],
                "total": detail["progress"]["total"],
                "sections": [
                    {
                        "name": s["name"],
                        "percent": s["progress"]["percent"],
                        "completed": s["progress"]["completed"],
                        "total": s["progress"]["total"],
                    }
                    for s in detail["sections"]
                ],
            }
        return self._builder().sheets()

    def _get_recent_activity(self, limit: int = 10) -> list[dict]:
        from app.analytics.activity import recent_activity

        return recent_activity(self.db, self.user_id, min(int(limit or 10), MAX_ITEMS))

    def _get_review_queue(self) -> dict:
        from app.services.review_service import count_due, get_due_reviews

        reviews = get_due_reviews(self.db, self.user_id, limit=MAX_ITEMS)
        return {
            "due_count": count_due(self.db, self.user_id),
            "items": [
                {
                    "problem": r.problem.title,
                    "reason": r.reason_detail or r.reason,
                    "scheduled_for": r.scheduled_for.isoformat(),
                }
                for r in reviews
            ],
        }

    def _get_contest_history(self, limit: int = 5) -> list[dict]:
        from app.services.contest_service import contest_history

        return contest_history(self.db, self.user_id, limit=min(int(limit or 5), 10))


def _topic_row(stats) -> dict[str, Any]:
    return {
        "name": stats.name,
        "solved": stats.solved,
        "attempted": stats.attempted,
        "success_rate": round(stats.success_rate, 3),
        "mastery_percent": round(stats.mastery, 1),
        "band": stats.band,
        "confidence": stats.confidence,
        "average_rating": round(stats.avg_rating) if stats.avg_rating else None,
        "average_time_minutes": round(stats.avg_time_minutes, 1)
        if stats.avg_time_minutes
        else None,
        "days_since_practice": stats.days_since_practice,
        "mistakes": stats.mistakes,
    }


def _sanitize(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop anything not declared in the schemas.

    Prevents a model from smuggling an unexpected keyword (notably `user_id`)
    into a handler.
    """
    allowed = {"topic", "pattern", "limit", "sheet"}
    return {k: v for k, v in (arguments or {}).items() if k in allowed}
