"""SQLAlchemy models.

Importing this package registers every mapper, which Alembic autogenerate and
`Base.metadata.create_all` both depend on.
"""

from app.db.base import Base
from app.models.ai import AIConversation, AIInsight, AIMessage, AIUsage
from app.models.contest import (
    Contest,
    ContestParticipation,
    ContestProblem,
    ContestProblemResult,
)
from app.models.editorial import Resource, TrustedChannel
from app.models.icpc import (
    HintReveal,
    ICPCSettings,
    ICPCTopicProgress,
    PracticeSession,
    ReadinessSnapshot,
    TemplateReview,
    VirtualContest,
    VirtualContestProblem,
)
from app.models.gamification import (
    Achievement,
    ActivityDay,
    DailyGoal,
    DailyMission,
    StreakFreezeTransaction,
    UserAchievement,
    UserStats,
    WeeklyGoal,
    XPTransaction,
)
from app.models.problem import Pattern, Problem, ProblemPattern, ProblemTopic, Topic
from app.models.progress import (
    Mistake,
    ProblemNote,
    Review,
    SolvingSession,
    Submission,
    UserProblem,
)
from app.models.recommendation import Recommendation, SyncRun
from app.models.sheet import (
    Collection,
    CollectionProblem,
    Sheet,
    SheetProblem,
    SheetSection,
)
from app.models.user import PlatformAccount, Profile, UserSettings

__all__ = [
    "Base",
    "Profile",
    "UserSettings",
    "PlatformAccount",
    "Problem",
    "Topic",
    "Pattern",
    "ProblemTopic",
    "ProblemPattern",
    "Sheet",
    "SheetSection",
    "SheetProblem",
    "Collection",
    "CollectionProblem",
    "UserProblem",
    "Submission",
    "SolvingSession",
    "Mistake",
    "ProblemNote",
    "Review",
    "UserStats",
    "ActivityDay",
    "XPTransaction",
    "StreakFreezeTransaction",
    "Achievement",
    "UserAchievement",
    "DailyGoal",
    "WeeklyGoal",
    "DailyMission",
    "Contest",
    "ContestProblem",
    "ContestParticipation",
    "ContestProblemResult",
    "Resource",
    "TrustedChannel",
    "AIInsight",
    "AIConversation",
    "AIMessage",
    "AIUsage",
    "Recommendation",
    "SyncRun",
    "ICPCSettings",
    "ICPCTopicProgress",
    "TemplateReview",
    "VirtualContest",
    "VirtualContestProblem",
    "PracticeSession",
    "HintReveal",
    "ReadinessSnapshot",
]
