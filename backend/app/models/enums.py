"""Domain enumerations.

Stored as plain strings rather than Postgres ENUM types: adding a value to a
native enum requires a migration and locks the table, and these vocabularies
are expected to grow.
"""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    """Where a canonical problem lives.

    `TAKEUFORWARD` exists because 211 of the 474 Striver A2Z entries have no
    LeetCode link at all — they are takeUforward's own problems and articles.
    Slugifying their titles into LeetCode-shaped ids would invent identities
    for problems that do not exist there, so they get an honest platform of
    their own. It carries no submission API, so it is deliberately absent from
    the account-linking and sync allowlists.
    """

    LEETCODE = "leetcode"
    CODEFORCES = "codeforces"
    TAKEUFORWARD = "takeuforward"


#: Platforms a user can link an account to and sync submissions from.
SYNCABLE_PLATFORMS = (Platform.CODEFORCES, Platform.LEETCODE)


class ContestPlatform(StrEnum):
    """Contests may come from platforms that are not problem sources.

    CodeChef is deliberately a contest-only platform: it is not part of the
    CP-31 / Striver problem taxonomy.
    """

    LEETCODE = "leetcode"
    CODEFORCES = "codeforces"
    CODECHEF = "codechef"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    UNKNOWN = "unknown"


class ProblemStatus(StrEnum):
    UNSOLVED = "unsolved"
    ATTEMPTED = "attempted"
    SOLVED = "solved"
    REVISIT = "revisit"
    MASTERED = "mastered"
    SKIPPED = "skipped"


class SolutionSource(StrEnum):
    """How much help the solve required. Not all solves are equal.

    `UNKNOWN` is what a platform sync produces: Codeforces and LeetCode tell us
    a problem was accepted, never whether an editorial was open in the next
    tab. Recording those as `INDEPENDENT` would quietly inflate every
    independence statistic, so they stay honestly unlabelled until the user
    says otherwise.
    """

    INDEPENDENT = "independent"
    HINT = "hint"
    EDITORIAL = "editorial"
    DISCUSSION = "discussion"
    COPIED = "copied"
    UNKNOWN = "unknown"


#: Weight applied to a solve when computing mastery. An editorial-assisted
#: solve is genuine progress, but it is weaker evidence of mastery. Unknown
#: sits mid-scale — neither rewarded nor punished for missing information.
SOLUTION_SOURCE_WEIGHT: dict[str, float] = {
    SolutionSource.INDEPENDENT: 1.0,
    SolutionSource.HINT: 0.7,
    SolutionSource.UNKNOWN: 0.6,
    SolutionSource.EDITORIAL: 0.4,
    SolutionSource.DISCUSSION: 0.4,
    SolutionSource.COPIED: 0.1,
}

#: Sources the user explicitly reported. Only these carry independence signal.
REPORTED_SOURCES = (
    SolutionSource.INDEPENDENT,
    SolutionSource.HINT,
    SolutionSource.EDITORIAL,
    SolutionSource.DISCUSSION,
    SolutionSource.COPIED,
)


class MistakeType(StrEnum):
    IMPLEMENTATION_BUG = "implementation_bug"
    WRONG_ALGORITHM = "wrong_algorithm"
    MISSED_EDGE_CASE = "missed_edge_case"
    INTEGER_OVERFLOW = "integer_overflow"
    OFF_BY_ONE = "off_by_one"
    WRONG_COMPLEXITY = "wrong_complexity"
    MISREAD_PROBLEM = "misread_problem"
    GREEDY_MISJUDGMENT = "greedy_misjudgment"
    DP_STATE_ERROR = "dp_state_error"
    GRAPH_MODELING_ERROR = "graph_modeling_error"
    PROOF_GAP = "proof_gap"
    MATH_ERROR = "math_error"
    BINARY_SEARCH_BOUNDARY = "binary_search_boundary"
    DATA_STRUCTURE_MISUSE = "data_structure_misuse"


MISTAKE_LABELS: dict[str, str] = {
    MistakeType.IMPLEMENTATION_BUG: "Implementation Bug",
    MistakeType.WRONG_ALGORITHM: "Wrong Algorithm",
    MistakeType.MISSED_EDGE_CASE: "Missed Edge Case",
    MistakeType.INTEGER_OVERFLOW: "Integer Overflow",
    MistakeType.OFF_BY_ONE: "Off-by-One",
    MistakeType.WRONG_COMPLEXITY: "Wrong Complexity",
    MistakeType.MISREAD_PROBLEM: "Misread Problem",
    MistakeType.GREEDY_MISJUDGMENT: "Greedy Misjudgment",
    MistakeType.DP_STATE_ERROR: "DP State Error",
    MistakeType.GRAPH_MODELING_ERROR: "Graph Modeling Error",
    MistakeType.PROOF_GAP: "Proof Gap",
    MistakeType.MATH_ERROR: "Math Error",
    MistakeType.BINARY_SEARCH_BOUNDARY: "Binary Search Boundary",
    MistakeType.DATA_STRUCTURE_MISUSE: "Data Structure Misuse",
}

#: Mistakes that indicate the approach was right but the code was not.
IMPLEMENTATION_MISTAKES = {
    MistakeType.IMPLEMENTATION_BUG,
    MistakeType.OFF_BY_ONE,
    MistakeType.INTEGER_OVERFLOW,
    MistakeType.MISSED_EDGE_CASE,
    MistakeType.BINARY_SEARCH_BOUNDARY,
}

#: Mistakes that indicate the approach itself was wrong.
CONCEPTUAL_MISTAKES = {
    MistakeType.WRONG_ALGORITHM,
    MistakeType.WRONG_COMPLEXITY,
    MistakeType.GREEDY_MISJUDGMENT,
    MistakeType.DP_STATE_ERROR,
    MistakeType.GRAPH_MODELING_ERROR,
    MistakeType.PROOF_GAP,
}


class NoteKind(StrEnum):
    INSIGHT = "insight"
    APPROACH = "approach"
    PROOF = "proof"
    COMPLEXITY = "complexity"
    MISTAKE = "mistake"
    ALTERNATIVE = "alternative"
    REMEMBER = "remember"


class TopicKind(StrEnum):
    TOPIC = "topic"
    SUBTOPIC = "subtopic"
    TECHNIQUE = "technique"
    ALGORITHM = "algorithm"


class SheetKind(StrEnum):
    A2Z = "a2z"
    CP31 = "cp31"
    CUSTOM = "custom"


class SectionKind(StrEnum):
    TOPIC = "topic"
    RATING_BUCKET = "rating_bucket"


class XPKind(StrEnum):
    FIRST_SOLVE = "first_solve"
    BONUS = "bonus"
    MISSION = "mission"
    ACHIEVEMENT = "achievement"
    PURCHASE = "purchase"
    ADJUSTMENT = "adjustment"


class FreezeKind(StrEnum):
    EARNED = "earned"
    PURCHASED = "purchased"
    USED = "used"
    EXPIRED = "expired"


class ContestSolveStatus(StrEnum):
    LIVE = "live"
    UPSOLVED = "upsolved"
    ATTEMPTED = "attempted"
    NOT_ATTEMPTED = "not_attempted"


class ResourceKind(StrEnum):
    EDITORIAL = "editorial"
    VIDEO = "video"
    CODE = "code"
    ARTICLE = "article"
    DISCUSSION = "discussion"


class SubmissionSource(StrEnum):
    SYNC = "sync"
    MANUAL = "manual"
    IMPORT = "import"


class ReviewReason(StrEnum):
    REPEATED_MISTAKE = "repeated_mistake"
    LOW_CONFIDENCE = "low_confidence"
    USED_EDITORIAL = "used_editorial"
    MULTIPLE_FAILURES = "multiple_failures"
    IMPORTANT_PATTERN = "important_pattern"
    STALE = "stale"
    MANUAL = "manual"


class AIInsightType(StrEnum):
    DAILY_INSIGHT = "daily_insight"
    WEEKLY_REVIEW = "weekly_review"
    MONTHLY_REVIEW = "monthly_review"
    WEAKNESS_ANALYSIS = "weakness_analysis"
    CONTEST_ANALYSIS = "contest_analysis"
    STUDY_PLAN = "study_plan"
    RECOMMENDATION_EXPLANATION = "recommendation_explanation"
    MISTAKE_ANALYSIS = "mistake_analysis"
    PROGRESS_ANALYSIS = "progress_analysis"
    COACH_CHAT = "coach_chat"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class InsightStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    FALLBACK = "fallback"
