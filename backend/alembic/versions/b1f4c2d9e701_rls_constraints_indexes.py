"""RLS policies, check constraints and performance indexes

Postgres/Supabase only. On SQLite (tests, local dev) this migration is a no-op:
SQLite has no row-level security and the application enforces the same scoping
in code.

Values in the CHECK constraints are deliberately hardcoded rather than derived
from `app.models.enums`. A migration is a frozen snapshot of history; if the
enums grow later, that is a new migration, not a silent change to this one.

Revision ID: b1f4c2d9e701
Revises: 3ee3a8277a90
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import app.db.types  # noqa: F401  (custom column types)

revision: str = "b1f4c2d9e701"
down_revision: str | None = "3ee3a8277a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PLATFORMS = ("leetcode", "codeforces")
CONTEST_PLATFORMS = ("leetcode", "codeforces", "codechef")
DIFFICULTIES = ("easy", "medium", "hard", "unknown")
PROBLEM_STATUSES = ("unsolved", "attempted", "solved", "revisit", "mastered", "skipped")
SOLUTION_SOURCES = (
    "independent",
    "hint",
    "editorial",
    "discussion",
    "copied",
    #: Platform sync records an accepted solve without knowing how much help
    #: it took; that is stored as `unknown` rather than assumed independent.
    "unknown",
)
FREEZE_KINDS = ("earned", "purchased", "used", "expired")
XP_KINDS = ("first_solve", "bonus", "mission", "achievement", "purchase", "adjustment")
CONTEST_SOLVE_STATUSES = ("live", "upsolved", "attempted", "not_attempted")
AI_CONFIDENCE = ("high", "medium", "low", "insufficient_data")

#: (table, column) -> user ownership is a plain column comparison.
USER_OWNED_TABLES = [
    "user_settings",
    "platform_accounts",
    "user_problems",
    "submissions",
    "solving_sessions",
    "mistakes",
    "problem_notes",
    "reviews",
    "user_stats",
    "activity_days",
    "xp_transactions",
    "streak_freeze_transactions",
    "user_achievements",
    "daily_goals",
    "weekly_goals",
    "daily_missions",
    "contest_participations",
    "contest_problem_results",
    "recommendations",
    "sync_runs",
    "ai_insights",
    "ai_conversations",
    "ai_messages",
    "ai_usage",
    "collections",
]

#: Shared catalog data. Readable by any signed-in user; only the backend
#: (service_role / direct connection) may write.
CATALOG_TABLES = [
    "problems",
    "topics",
    "patterns",
    "problem_topics",
    "problem_patterns",
    "sheets",
    "sheet_sections",
    "sheet_problems",
    "achievements",
    "contests",
    "contest_problems",
]

#: user_id is nullable: NULL rows are global defaults visible to everyone.
NULLABLE_OWNER_TABLES = ["resources", "trusted_channels"]


def _quote(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite: no RLS, and CHECK constraints would require table rebuilds
        # for no benefit in a single-user local database.
        return

    # -- extensions --------------------------------------------------------
    # pg_trgm powers fuzzy problem search without a separate search service.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # -- uuid primary key defaults ----------------------------------------
    # `gen_random_uuid()` is Postgres-only, so it cannot live on the models
    # (SQLite would reject the DDL). Applying it here means rows inserted
    # directly - by a trigger, by supabase-js, or by hand in the SQL editor -
    # get a valid id without relying on SQLAlchemy.
    op.execute(
        """
        DO $$
        DECLARE
            target record;
        BEGIN
            FOR target IN
                SELECT c.table_name
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.column_name = 'id'
                  AND c.data_type = 'uuid'
                  AND c.column_default IS NULL
            LOOP
                EXECUTE format(
                    'ALTER TABLE public.%I ALTER COLUMN id SET DEFAULT gen_random_uuid()',
                    target.table_name
                );
            END LOOP;
        END
        $$
        """
    )

    # -- check constraints -------------------------------------------------
    checks: list[tuple[str, str, str]] = [
        ("problems", "platform_valid", f"platform IN ({_quote(PLATFORMS)})"),
        ("problems", "difficulty_valid", f"difficulty IN ({_quote(DIFFICULTIES)})"),
        ("problems", "rating_range", "rating IS NULL OR (rating > 0 AND rating < 5000)"),
        (
            "problems",
            "acceptance_range",
            "acceptance_rate IS NULL OR (acceptance_rate >= 0 AND acceptance_rate <= 100)",
        ),
        ("platform_accounts", "platform_valid", f"platform IN ({_quote(PLATFORMS)})"),
        ("user_problems", "status_valid", f"status IN ({_quote(PROBLEM_STATUSES)})"),
        ("user_problems", "attempts_positive", "attempts >= 0"),
        ("user_problems", "solved_count_positive", "solved_count >= 0"),
        (
            "user_problems",
            "confidence_range",
            "confidence IS NULL OR (confidence >= 1 AND confidence <= 5)",
        ),
        (
            "user_problems",
            "solution_source_valid",
            f"best_solution_source IS NULL OR best_solution_source IN ({_quote(SOLUTION_SOURCES)})",
        ),
        ("submissions", "platform_valid", f"platform IN ({_quote(PLATFORMS)})"),
        (
            "solving_sessions",
            "solution_source_valid",
            f"solution_source IN ({_quote(SOLUTION_SOURCES)})",
        ),
        (
            "solving_sessions",
            "confidence_range",
            "confidence IS NULL OR (confidence >= 1 AND confidence <= 5)",
        ),
        (
            "solving_sessions",
            "perception_range",
            "difficulty_perception IS NULL OR (difficulty_perception >= 1 AND difficulty_perception <= 5)",
        ),
        (
            "solving_sessions",
            "time_positive",
            "time_spent_seconds IS NULL OR time_spent_seconds >= 0",
        ),
        ("xp_transactions", "amount_nonzero", "amount <> 0"),
        ("xp_transactions", "kind_valid", f"kind IN ({_quote(XP_KINDS)})"),
        (
            "streak_freeze_transactions",
            "kind_valid",
            f"kind IN ({_quote(FREEZE_KINDS)})",
        ),
        ("streak_freeze_transactions", "amount_positive", "amount > 0"),
        ("activity_days", "counters_positive", "problems_solved >= 0 AND submissions >= 0 AND minutes_spent >= 0"),
        ("daily_goals", "target_positive", "target > 0"),
        ("daily_missions", "target_positive", "target > 0"),
        ("weekly_goals", "target_positive", "target > 0"),
        ("user_settings", "daily_goal_positive", "daily_goal > 0"),
        ("user_settings", "max_freezes_range", "max_freezes >= 0 AND max_freezes <= 20"),
        ("user_settings", "freeze_cost_positive", "freeze_cost_xp >= 0"),
        ("contests", "platform_valid", f"platform IN ({_quote(CONTEST_PLATFORMS)})"),
        (
            "contest_problem_results",
            "status_valid",
            f"status IN ({_quote(CONTEST_SOLVE_STATUSES)})",
        ),
        ("ai_insights", "confidence_valid", f"confidence IN ({_quote(AI_CONFIDENCE)})"),
        ("ai_usage", "tokens_positive", "input_tokens >= 0 AND output_tokens >= 0"),
    ]
    for table, name, expression in checks:
        op.create_check_constraint(name, table, expression)

    # -- indexes -----------------------------------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_problems_title_trgm "
        "ON problems USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_problems_external_lookup "
        "ON problems (platform, external_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_submissions_user_accepted_time "
        "ON submissions (user_id, is_accepted, submitted_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_problems_user_first_solved "
        "ON user_problems (user_id, first_solved_at DESC) "
        "WHERE first_solved_at IS NOT NULL"
    )
    # Partial indexes: the queries that matter only ever look at open rows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reviews_open "
        "ON reviews (user_id, scheduled_for) WHERE completed_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_recommendations_active "
        "ON recommendations (user_id, score DESC) "
        "WHERE expires_at IS NULL AND dismissed_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_problems_review_due_open "
        "ON user_problems (user_id, review_due_at) WHERE needs_review = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_insights_lookup "
        "ON ai_insights (user_id, type, generated_at DESC)"
    )

    # -- row level security ------------------------------------------------
    # NOTE: the FastAPI backend connects with a privileged role that bypasses
    # RLS by design; it enforces the same scoping in code from the verified
    # JWT. These policies protect direct client access (supabase-js) and act as
    # defence in depth. See docs/database.md.

    op.execute("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY profiles_self_select ON profiles
            FOR SELECT TO authenticated USING (id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY profiles_self_update ON profiles
            FOR UPDATE TO authenticated
            USING (id = auth.uid()) WITH CHECK (id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY profiles_self_insert ON profiles
            FOR INSERT TO authenticated WITH CHECK (id = auth.uid())
        """
    )

    for table in USER_OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_owner_all ON {table}
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid())
            """
        )

    # collection_problems has no user_id; ownership flows through the parent.
    op.execute("ALTER TABLE collection_problems ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY collection_problems_owner_all ON collection_problems
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM collections c
                    WHERE c.id = collection_problems.collection_id
                      AND c.user_id = auth.uid()
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM collections c
                    WHERE c.id = collection_problems.collection_id
                      AND c.user_id = auth.uid()
                )
            )
        """
    )

    for table in NULLABLE_OWNER_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_read ON {table}
                FOR SELECT TO authenticated
                USING (user_id IS NULL OR user_id = auth.uid())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_write ON {table}
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid())
            """
        )

    for table in CATALOG_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_read ON {table}
                FOR SELECT TO authenticated USING (true)
            """
        )

    # -- profile provisioning ---------------------------------------------
    # Create the CP-Forge profile (and its dependents) the moment a Supabase
    # auth user is created, so a fresh sign-up lands on a working dashboard.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
            INSERT INTO public.profiles (id, email, username, timezone, created_at, updated_at)
            VALUES (
                NEW.id,
                NEW.email,
                COALESCE(
                    NEW.raw_user_meta_data->>'username',
                    split_part(COALESCE(NEW.email, 'user'), '@', 1)
                ),
                COALESCE(NEW.raw_user_meta_data->>'timezone', 'UTC'),
                now(),
                now()
            )
            ON CONFLICT (id) DO NOTHING;

            INSERT INTO public.user_settings (user_id, created_at, updated_at)
            VALUES (NEW.id, now(), now())
            ON CONFLICT (user_id) DO NOTHING;

            INSERT INTO public.user_stats (user_id, created_at, updated_at)
            VALUES (NEW.id, now(), now())
            ON CONFLICT (user_id) DO NOTHING;

            RETURN NEW;
        END;
        $$
        """
    )
    # Guarded: plain Postgres has no auth schema, only Supabase does.
    op.execute(
        """
        DO $$
        BEGIN
            -- Guard on the TABLE, not the schema. A plain Postgres instance may
            -- have an `auth` schema (for an auth.uid() shim) without Supabase's
            -- auth.users table, and referencing it would abort the migration.
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'auth' AND table_name = 'users'
            ) THEN
                DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
                CREATE TRIGGER on_auth_user_created
                    AFTER INSERT ON auth.users
                    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            -- Guard on the TABLE, not the schema. A plain Postgres instance may
            -- have an `auth` schema (for an auth.uid() shim) without Supabase's
            -- auth.users table, and referencing it would abort the migration.
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'auth' AND table_name = 'users'
            ) THEN
                DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
            END IF;
        END
        $$
        """
    )
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_auth_user()")

    for table in CATALOG_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for table in NULLABLE_OWNER_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_write ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS collection_problems_owner_all ON collection_problems")
    op.execute("ALTER TABLE collection_problems DISABLE ROW LEVEL SECURITY")

    for table in USER_OWNED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner_all ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for policy in ("profiles_self_select", "profiles_self_update", "profiles_self_insert"):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON profiles")
    op.execute("ALTER TABLE profiles DISABLE ROW LEVEL SECURITY")

    for index in (
        "ix_problems_title_trgm",
        "ix_problems_external_lookup",
        "ix_submissions_user_accepted_time",
        "ix_user_problems_user_first_solved",
        "ix_reviews_open",
        "ix_recommendations_active",
        "ix_user_problems_review_due_open",
        "ix_ai_insights_lookup",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")

    for table, name, _ in _CHECK_CONSTRAINTS_FOR_DOWNGRADE:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{name}")


_CHECK_CONSTRAINTS_FOR_DOWNGRADE = [
    ("problems", "platform_valid", ""),
    ("problems", "difficulty_valid", ""),
    ("problems", "rating_range", ""),
    ("problems", "acceptance_range", ""),
    ("platform_accounts", "platform_valid", ""),
    ("user_problems", "status_valid", ""),
    ("user_problems", "attempts_positive", ""),
    ("user_problems", "solved_count_positive", ""),
    ("user_problems", "confidence_range", ""),
    ("user_problems", "solution_source_valid", ""),
    ("submissions", "platform_valid", ""),
    ("solving_sessions", "solution_source_valid", ""),
    ("solving_sessions", "confidence_range", ""),
    ("solving_sessions", "perception_range", ""),
    ("solving_sessions", "time_positive", ""),
    ("xp_transactions", "amount_nonzero", ""),
    ("xp_transactions", "kind_valid", ""),
    ("streak_freeze_transactions", "kind_valid", ""),
    ("streak_freeze_transactions", "amount_positive", ""),
    ("activity_days", "counters_positive", ""),
    ("daily_goals", "target_positive", ""),
    ("daily_missions", "target_positive", ""),
    ("weekly_goals", "target_positive", ""),
    ("user_settings", "daily_goal_positive", ""),
    ("user_settings", "max_freezes_range", ""),
    ("user_settings", "freeze_cost_positive", ""),
    ("contests", "platform_valid", ""),
    ("contest_problem_results", "status_valid", ""),
    ("ai_insights", "confidence_valid", ""),
    ("ai_usage", "tokens_positive", ""),
]
