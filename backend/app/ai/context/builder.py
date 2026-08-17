"""AI context builder.

Turns the deterministic analytics into a compact, structured fact sheet.

Two rules:

1. The model receives *computed metrics*, never raw database rows, and never
   the whole database.
2. The model is never asked to compute a statistic. It interprets numbers that
   the analytics engine already established as true.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.activity import weekly_totals
from app.analytics.mastery import pattern_mastery, topic_mastery, untouched_topics
from app.analytics.stats import (
    difficulty_progression,
    mistake_distribution,
    overview,
)
from app.analytics.weakness import detect_weaknesses
from app.gamification.streaks import compute_streak
from app.gamification.xp import level_info
from app.models.user import Profile, UserSettings
from app.services.review_service import count_due


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


class AIContextBuilder:
    """Builds the structured context for each insight type."""

    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id
        profile = db.get(Profile, user_id)
        self.tz = profile.timezone if profile else "UTC"
        self.username = profile.username if profile else "user"

    # -- shared blocks ----------------------------------------------------

    def user_summary(self) -> dict[str, Any]:
        streak = compute_streak(self.db, self.user_id, self.tz)
        level = level_info(self.db, self.user_id)
        return {
            "current_streak_days": streak.current,
            "longest_streak_days": streak.longest,
            "active_today": streak.active_today,
            "level": level.level,
            "rank": level.rank,
            "total_xp": level.total_xp,
            "reviews_due": count_due(self.db, self.user_id),
        }

    def practice(self) -> dict[str, Any]:
        summary = overview(self.db, self.user_id, self.tz)
        return {
            "problems_solved_total": summary["volume"]["solved_total"],
            "problems_solved_last_7_days": summary["volume"]["solved_last_7_days"],
            "problems_solved_previous_7_days": summary["volume"]["solved_previous_7_days"],
            "problems_solved_last_30_days": summary["volume"]["solved_last_30_days"],
            "problems_solved_previous_30_days": summary["volume"]["solved_previous_30_days"],
            "volume_change_30d_percent": summary["volume"]["volume_change_30d"],
            "overall_success_rate": summary["success_rate"],
            "average_solve_time_minutes": summary["time"]["average_solve_minutes"],
            "median_solve_time_minutes": summary["time"]["median_solve_minutes"],
            "independent_solve_rate": summary["independence"]["independent_rate"],
            "editorial_solve_rate": summary["independence"]["editorial_rate"],
            "self_reported_solves": summary["independence"]["reported_solves"],
            "unreported_solves": summary["independence"]["unreported_solves"],
            "independence_note": (
                "Independence rates are shares of self-reported solves only. "
                "Solves imported from a platform sync carry no self-report."
            ),
        }

    def difficulty(self) -> dict[str, Any]:
        summary = overview(self.db, self.user_id, self.tz)["difficulty"]
        return {
            "average_cf_rating": summary["average_cf_rating"],
            "median_cf_rating": summary["median_cf_rating"],
            "highest_cf_rating": summary["highest_cf_rating"],
            "average_cf_rating_last_30_days": summary["average_cf_rating_last_30_days"],
            "average_cf_rating_previous_30_days": summary[
                "average_cf_rating_previous_30_days"
            ],
            "rating_change_30d": summary["rating_change_30d"],
            "comfortable_rating": summary["comfortable_rating"],
            "leetcode_difficulty_counts": summary["leetcode_difficulty_counts"],
            "comfortable_rating_definition": (
                "Highest 100-point band with at least 3 solves and a 60%+ "
                "success rate. Not the single hardest problem ever solved."
            ),
        }

    def weak_topics(self, limit: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "topic": w.name,
                "kind": w.kind,
                "mastery_percent": round(w.mastery, 1),
                "severity": w.severity,
                "confidence": w.confidence,
                "root_cause": w.root_cause_label,
                "signals": w.signals,
                "evidence": [e["description"] for e in w.evidence],
                "recommended_difficulty": w.recommended_difficulty,
            }
            for w in detect_weaknesses(self.db, self.user_id, self.tz, limit=limit)
        ]

    def strong_topics(self, limit: int = 5) -> list[dict[str, Any]]:
        mastery = topic_mastery(self.db, self.user_id, self.tz)
        confident = [m for m in mastery if m.confidence not in ("insufficient_data",)]
        return [
            {
                "topic": m.name,
                "mastery_percent": round(m.mastery, 1),
                "solved": m.solved,
                "success_rate": _round(m.success_rate),
            }
            for m in sorted(confident, key=lambda m: -m.mastery)[:limit]
        ]

    def patterns(self, limit: int = 8) -> list[dict[str, Any]]:
        return [
            {
                "pattern": m.name,
                "solved": m.solved,
                "mastery_percent": round(m.mastery, 1),
                "success_rate": _round(m.success_rate),
                "days_since_practice": m.days_since_practice,
                "average_rating": _round(m.avg_rating, 0),
            }
            for m in pattern_mastery(self.db, self.user_id, self.tz)[:limit]
        ]

    def mistakes(self) -> dict[str, Any]:
        distribution = mistake_distribution(self.db, self.user_id, limit=6)
        return {
            "total_recorded": distribution["total"],
            "top": [
                {"type": item["label"], "count": item["count"], "share": item["share"]}
                for item in distribution["items"]
            ],
            "implementation_count": distribution["implementation_count"],
            "conceptual_count": distribution["conceptual_count"],
            "implementation_share": distribution["implementation_share"],
        }

    def sheets(self) -> dict[str, Any]:
        from app.services.sheet_service import list_sheets

        return {
            sheet["slug"]: {
                "name": sheet["name"],
                "completed": sheet["progress"]["completed"],
                "total": sheet["progress"]["total"],
                "percent": sheet["progress"]["percent"],
            }
            for sheet in list_sheets(self.db, self.user_id)
        }

    def goals(self) -> dict[str, Any]:
        config = self.db.get(UserSettings, self.user_id)
        return {
            "daily_problem_goal": config.daily_goal if config else 2,
            "weekly_problem_goal": config.weekly_goal if config else 14,
        }

    def recommended_problems(self, limit: int = 5) -> list[dict[str, Any]]:
        """Candidates chosen by the deterministic engine.

        The model explains these; it never selects its own.
        """
        from app.recommendations.engine import get_recommendations

        return [
            {
                "problem": r["problem"]["title"],
                "platform": r["problem"]["platform"],
                "id": r["problem"]["external_id"],
                "rating": r["problem"]["rating"],
                "why_selected": r["reason_text"],
                "expected_xp": r["expected_xp"],
            }
            for r in get_recommendations(self.db, self.user_id, limit=limit, tz=self.tz)
        ]

    # -- per-insight contexts ---------------------------------------------

    def daily(self) -> dict[str, Any]:
        return {
            "user": self.user_summary(),
            "practice": self.practice(),
            "difficulty": self.difficulty(),
            "weak_topics": self.weak_topics(3),
            "goals": self.goals(),
            "recommended_problems": self.recommended_problems(3),
        }

    def weekly(self) -> dict[str, Any]:
        return {
            "user": self.user_summary(),
            "practice": self.practice(),
            "difficulty": self.difficulty(),
            "weak_topics": self.weak_topics(5),
            "strong_topics": self.strong_topics(4),
            "patterns": self.patterns(6),
            "mistakes": self.mistakes(),
            "sheets": self.sheets(),
            "goals": self.goals(),
            "weekly_activity": weekly_totals(self.db, self.user_id, self.tz, weeks=6),
        }

    def weakness(self) -> dict[str, Any]:
        return {
            "user": self.user_summary(),
            "practice": self.practice(),
            "difficulty": self.difficulty(),
            "weak_topics": self.weak_topics(6),
            "strong_topics": self.strong_topics(3),
            "patterns": self.patterns(8),
            "mistakes": self.mistakes(),
            "untouched_topics": untouched_topics(self.db, self.user_id)[:8],
        }

    def progress(self) -> dict[str, Any]:
        return {
            "user": self.user_summary(),
            "practice": self.practice(),
            "difficulty": self.difficulty(),
            "progression": difficulty_progression(self.db, self.user_id, months=6),
            "sheets": self.sheets(),
        }

    def study_plan(self, available_days: int = 7) -> dict[str, Any]:
        return {
            "user": self.user_summary(),
            "goals": {**self.goals(), "available_days_this_week": available_days},
            "practice": self.practice(),
            "difficulty": self.difficulty(),
            "weak_topics": self.weak_topics(4),
            "sheets": self.sheets(),
            "reviews_due": count_due(self.db, self.user_id),
        }

    def for_type(self, insight_type: str) -> dict[str, Any]:
        from app.models.enums import AIInsightType

        mapping = {
            AIInsightType.DAILY_INSIGHT: self.daily,
            AIInsightType.WEEKLY_REVIEW: self.weekly,
            AIInsightType.MONTHLY_REVIEW: self.weekly,
            AIInsightType.WEAKNESS_ANALYSIS: self.weakness,
            AIInsightType.PROGRESS_ANALYSIS: self.progress,
            AIInsightType.MISTAKE_ANALYSIS: self.weakness,
            AIInsightType.STUDY_PLAN: self.study_plan,
        }
        builder = mapping.get(insight_type, self.daily)
        return builder()


def snapshot_hash(context: dict[str, Any]) -> str:
    """Stable fingerprint of the metrics behind an insight.

    Identical metrics produce an identical hash, so a cached insight is reused
    instead of spending tokens re-describing unchanged numbers.
    """
    encoded = json.dumps(context, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]
