"""Dashboard aggregation.

One endpoint assembles the whole home screen so the frontend makes a single
request instead of a waterfall. AI is deliberately excluded — it is fetched
separately so a slow or missing model never delays the dashboard.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.activity import heatmap, recent_activity
from app.analytics.stats import comfortable_rating, overview
from app.analytics.weakness import weakness_summary
from app.gamification.streaks import roll_over_streak
from app.gamification.xp import level_info
from app.models.gamification import DailyGoal, UserStats
from app.models.user import Profile
from app.recommendations.engine import get_recommendations
from app.services.mission_service import missions_for_today
from app.services.review_service import count_due
from app.services.sheet_service import list_sheets
from app.utils.timeutils import today_in


def build_dashboard(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    profile = db.get(Profile, user_id)
    tz = profile.timezone if profile else "UTC"
    today = today_in(tz)

    # Applies any pending streak freezes before reporting the streak.
    streak = roll_over_streak(db, user_id)
    level = level_info(db, user_id)
    stats = db.get(UserStats, user_id)

    goal = db.scalar(
        select(DailyGoal).where(
            DailyGoal.user_id == user_id, DailyGoal.goal_date == today
        )
    )

    summary = overview(db, user_id, tz)
    weaknesses = weakness_summary(db, user_id, tz)
    sheets = list_sheets(db, user_id)

    return {
        "user": {
            "id": str(user_id),
            "username": profile.username if profile else "",
            "display_name": profile.display_name if profile else None,
            "timezone": tz,
        },
        "level": level.as_dict(),
        "streak": {
            "current": streak.current,
            "longest": streak.longest,
            "active_today": streak.active_today,
            "freezes_available": streak.freezes_available,
            "last_active_date": streak.last_active_date.isoformat()
            if streak.last_active_date
            else None,
        },
        "daily_goal": {
            "target": goal.target if goal else 2,
            "progress": goal.progress if goal else 0,
            "completed": bool(goal and goal.completed_at),
        },
        "totals": {
            "problems_solved": stats.problems_solved if stats else 0,
            "independent_solves": stats.independent_solves if stats else 0,
            "total_xp": level.total_xp,
            "reviews_due": count_due(db, user_id),
        },
        "difficulty": {
            "average_cf_rating": summary["difficulty"]["average_cf_rating"],
            "highest_cf_rating": summary["difficulty"]["highest_cf_rating"],
            "comfortable_rating": comfortable_rating(db, user_id),
            "rating_change_30d": summary["difficulty"]["rating_change_30d"],
        },
        "volume": summary["volume"],
        "independence": summary["independence"],
        "missions": missions_for_today(db, user_id, tz),
        "recommendations": get_recommendations(db, user_id, limit=4, tz=tz),
        "weaknesses": weaknesses["weaknesses"][:4],
        "has_enough_data": weaknesses["has_enough_data"],
        "sheets": [
            {
                "slug": sheet["slug"],
                "name": sheet["name"],
                "kind": sheet["kind"],
                "percent": sheet["progress"]["percent"],
                "completed": sheet["progress"]["completed"],
                "total": sheet["progress"]["total"],
            }
            for sheet in sheets
        ],
        "heatmap": heatmap(db, user_id, tz, days=365),
        "recent_activity": recent_activity(db, user_id, limit=8),
    }
