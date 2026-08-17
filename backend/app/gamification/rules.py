"""XP and level rules.

Nothing in the application hardcodes an XP number. Rules resolve from
per-user overrides first, then these defaults, so tuning the economy is a
settings change rather than a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.enums import Difficulty, Platform

#: LeetCode difficulty -> XP.
DEFAULT_LEETCODE_XP: dict[str, int] = {
    Difficulty.EASY: 10,
    Difficulty.MEDIUM: 20,
    Difficulty.HARD: 40,
    Difficulty.UNKNOWN: 10,
}

#: Codeforces rating bands -> XP. `(inclusive_min, xp)`, highest match wins.
DEFAULT_CODEFORCES_XP: list[tuple[int, int]] = [
    (0, 10),
    (1000, 15),
    (1200, 20),
    (1400, 30),
    (1600, 40),
    (1800, 60),
]

#: Bonus awards. Each is granted at most once per its dedupe scope.
DEFAULT_BONUS_XP: dict[str, int] = {
    "first_problem_of_day": 5,
    "daily_goal_completed": 15,
    "weekly_goal_completed": 50,
    "contest_participation": 50,
    "upsolve": 15,
    "above_average_difficulty": 10,
    "topic_completed": 100,
    "cp31_bucket_completed": 200,
    "sheet_section_completed": 75,
    "mission_completed": 25,
    "review_completed": 5,
    "streak_milestone": 25,
}

#: Level rank names, applied from the highest threshold at or below the level.
DEFAULT_RANKS: list[tuple[int, str]] = [
    (1, "Novice"),
    (3, "Beginner"),
    (5, "Problem Solver"),
    (8, "Practitioner"),
    (10, "Algorithmist"),
    (14, "Specialist"),
    (17, "Tactician"),
    (20, "Competitive Programmer"),
    (24, "Strategist"),
    (27, "Veteran"),
    (30, "Advanced"),
    (34, "Elite"),
    (37, "Master"),
    (40, "Expert"),
    (44, "Grandmaster"),
    (47, "Legend"),
    (50, "ICPC Hunter"),
]

MAX_LEVEL = 50
#: Cumulative XP required to *reach* level L. Superlinear so early levels are
#: quick and later ones represent real volume.
_LEVEL_COEFFICIENT = 120
_LEVEL_EXPONENT = 1.7


def xp_threshold_for_level(level: int) -> int:
    if level <= 1:
        return 0
    return round(_LEVEL_COEFFICIENT * ((level - 1) ** _LEVEL_EXPONENT))


def build_level_table(overrides: list[dict] | None = None) -> list[dict[str, Any]]:
    """The full level ladder. `overrides` replaces it entirely when provided."""
    if overrides:
        return [
            {
                "level": int(row["level"]),
                "xp_required": int(row["xp_required"]),
                "rank": str(row.get("rank", "")),
            }
            for row in sorted(overrides, key=lambda r: int(r["level"]))
        ]

    table: list[dict[str, Any]] = []
    for level in range(1, MAX_LEVEL + 1):
        rank = DEFAULT_RANKS[0][1]
        for threshold_level, name in DEFAULT_RANKS:
            if level >= threshold_level:
                rank = name
        table.append(
            {"level": level, "xp_required": xp_threshold_for_level(level), "rank": rank}
        )
    return table


@dataclass(frozen=True)
class LevelInfo:
    level: int
    rank: str
    total_xp: int
    current_level_xp: int
    xp_into_level: int
    xp_for_next_level: int | None
    xp_to_next_level: int | None
    progress: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "rank": self.rank,
            "total_xp": self.total_xp,
            "xp_into_level": self.xp_into_level,
            "xp_for_next_level": self.xp_for_next_level,
            "xp_to_next_level": self.xp_to_next_level,
            "progress": round(self.progress, 4),
        }


def level_for_xp(total_xp: int, overrides: list[dict] | None = None) -> LevelInfo:
    table = build_level_table(overrides)
    total_xp = max(0, int(total_xp))

    current = table[0]
    for row in table:
        if total_xp >= row["xp_required"]:
            current = row
        else:
            break

    next_row = next((r for r in table if r["level"] == current["level"] + 1), None)
    xp_into = total_xp - current["xp_required"]

    if next_row is None:
        return LevelInfo(
            level=current["level"],
            rank=current["rank"],
            total_xp=total_xp,
            current_level_xp=current["xp_required"],
            xp_into_level=xp_into,
            xp_for_next_level=None,
            xp_to_next_level=None,
            progress=1.0,
        )

    span = max(1, next_row["xp_required"] - current["xp_required"])
    return LevelInfo(
        level=current["level"],
        rank=current["rank"],
        total_xp=total_xp,
        current_level_xp=current["xp_required"],
        xp_into_level=xp_into,
        xp_for_next_level=next_row["xp_required"],
        xp_to_next_level=next_row["xp_required"] - total_xp,
        progress=min(1.0, xp_into / span),
    )


@dataclass(frozen=True)
class XPRules:
    leetcode: dict[str, int]
    codeforces: list[tuple[int, int]]
    bonus: dict[str, int]

    def for_problem(self, platform: str, difficulty: str, rating: int | None) -> int:
        """Base XP for a first solve."""
        if platform == Platform.CODEFORCES:
            if rating is None:
                # An unrated Codeforces problem is worth the entry band rather
                # than zero — the solve still happened.
                return self.codeforces[0][1]
            awarded = self.codeforces[0][1]
            for threshold, xp in self.codeforces:
                if rating >= threshold:
                    awarded = xp
            return awarded
        return self.leetcode.get(difficulty, self.leetcode[Difficulty.UNKNOWN])

    def bonus_for(self, key: str) -> int:
        return self.bonus.get(key, 0)


def resolve_rules(override: dict | None = None) -> XPRules:
    """Merge a user's `xp_rules_override` over the defaults."""
    leetcode = dict(DEFAULT_LEETCODE_XP)
    codeforces = list(DEFAULT_CODEFORCES_XP)
    bonus = dict(DEFAULT_BONUS_XP)

    if override:
        for key, value in (override.get("leetcode") or {}).items():
            leetcode[str(key).lower()] = int(value)
        if override.get("codeforces"):
            codeforces = sorted(
                (int(t), int(x)) for t, x in override["codeforces"]
            )
        for key, value in (override.get("bonus") or {}).items():
            bonus[str(key)] = int(value)

    return XPRules(leetcode=leetcode, codeforces=codeforces, bonus=bonus)
