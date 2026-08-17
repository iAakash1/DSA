-- ---------------------------------------------------------------------------
-- GENERATED FILE — DO NOT EDIT BY HAND.
--
-- Produced by: python scripts/generate_supabase_migrations.py
-- Source:      backend/alembic/versions/b1f4c2d9e701_rls_constraints_indexes.py
--
-- To change the schema: add an Alembic revision in backend/alembic/versions,
-- then re-run the generator. Editing this file directly will be overwritten
-- and will desynchronise the ORM models from the database.
-- ---------------------------------------------------------------------------

-- Running upgrade 3ee3a8277a90 -> b1f4c2d9e701

CREATE EXTENSION IF NOT EXISTS pg_trgm;

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
        $$;

ALTER TABLE problems ADD CONSTRAINT ck_problems_platform_valid CHECK (platform IN ('leetcode', 'codeforces'));

ALTER TABLE problems ADD CONSTRAINT ck_problems_difficulty_valid CHECK (difficulty IN ('easy', 'medium', 'hard', 'unknown'));

ALTER TABLE problems ADD CONSTRAINT ck_problems_rating_range CHECK (rating IS NULL OR (rating > 0 AND rating < 5000));

ALTER TABLE problems ADD CONSTRAINT ck_problems_acceptance_range CHECK (acceptance_rate IS NULL OR (acceptance_rate >= 0 AND acceptance_rate <= 100));

ALTER TABLE platform_accounts ADD CONSTRAINT ck_platform_accounts_platform_valid CHECK (platform IN ('leetcode', 'codeforces'));

ALTER TABLE user_problems ADD CONSTRAINT ck_user_problems_status_valid CHECK (status IN ('unsolved', 'attempted', 'solved', 'revisit', 'mastered', 'skipped'));

ALTER TABLE user_problems ADD CONSTRAINT ck_user_problems_attempts_positive CHECK (attempts >= 0);

ALTER TABLE user_problems ADD CONSTRAINT ck_user_problems_solved_count_positive CHECK (solved_count >= 0);

ALTER TABLE user_problems ADD CONSTRAINT ck_user_problems_confidence_range CHECK (confidence IS NULL OR (confidence >= 1 AND confidence <= 5));

ALTER TABLE user_problems ADD CONSTRAINT ck_user_problems_solution_source_valid CHECK (best_solution_source IS NULL OR best_solution_source IN ('independent', 'hint', 'editorial', 'discussion', 'copied', 'unknown'));

ALTER TABLE submissions ADD CONSTRAINT ck_submissions_platform_valid CHECK (platform IN ('leetcode', 'codeforces'));

ALTER TABLE solving_sessions ADD CONSTRAINT ck_solving_sessions_solution_source_valid CHECK (solution_source IN ('independent', 'hint', 'editorial', 'discussion', 'copied', 'unknown'));

ALTER TABLE solving_sessions ADD CONSTRAINT ck_solving_sessions_confidence_range CHECK (confidence IS NULL OR (confidence >= 1 AND confidence <= 5));

ALTER TABLE solving_sessions ADD CONSTRAINT ck_solving_sessions_perception_range CHECK (difficulty_perception IS NULL OR (difficulty_perception >= 1 AND difficulty_perception <= 5));

ALTER TABLE solving_sessions ADD CONSTRAINT ck_solving_sessions_time_positive CHECK (time_spent_seconds IS NULL OR time_spent_seconds >= 0);

ALTER TABLE xp_transactions ADD CONSTRAINT ck_xp_transactions_amount_nonzero CHECK (amount <> 0);

ALTER TABLE xp_transactions ADD CONSTRAINT ck_xp_transactions_kind_valid CHECK (kind IN ('first_solve', 'bonus', 'mission', 'achievement', 'purchase', 'adjustment'));

ALTER TABLE streak_freeze_transactions ADD CONSTRAINT ck_streak_freeze_transactions_kind_valid CHECK (kind IN ('earned', 'purchased', 'used', 'expired'));

ALTER TABLE streak_freeze_transactions ADD CONSTRAINT ck_streak_freeze_transactions_amount_positive CHECK (amount > 0);

ALTER TABLE activity_days ADD CONSTRAINT ck_activity_days_counters_positive CHECK (problems_solved >= 0 AND submissions >= 0 AND minutes_spent >= 0);

ALTER TABLE daily_goals ADD CONSTRAINT ck_daily_goals_target_positive CHECK (target > 0);

ALTER TABLE daily_missions ADD CONSTRAINT ck_daily_missions_target_positive CHECK (target > 0);

ALTER TABLE weekly_goals ADD CONSTRAINT ck_weekly_goals_target_positive CHECK (target > 0);

ALTER TABLE user_settings ADD CONSTRAINT ck_user_settings_daily_goal_positive CHECK (daily_goal > 0);

ALTER TABLE user_settings ADD CONSTRAINT ck_user_settings_max_freezes_range CHECK (max_freezes >= 0 AND max_freezes <= 20);

ALTER TABLE user_settings ADD CONSTRAINT ck_user_settings_freeze_cost_positive CHECK (freeze_cost_xp >= 0);

ALTER TABLE contests ADD CONSTRAINT ck_contests_platform_valid CHECK (platform IN ('leetcode', 'codeforces', 'codechef'));

ALTER TABLE contest_problem_results ADD CONSTRAINT ck_contest_problem_results_status_valid CHECK (status IN ('live', 'upsolved', 'attempted', 'not_attempted'));

ALTER TABLE ai_insights ADD CONSTRAINT ck_ai_insights_confidence_valid CHECK (confidence IN ('high', 'medium', 'low', 'insufficient_data'));

ALTER TABLE ai_usage ADD CONSTRAINT ck_ai_usage_tokens_positive CHECK (input_tokens >= 0 AND output_tokens >= 0);

CREATE INDEX IF NOT EXISTS ix_problems_title_trgm ON problems USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_problems_external_lookup ON problems (platform, external_id);

CREATE INDEX IF NOT EXISTS ix_submissions_user_accepted_time ON submissions (user_id, is_accepted, submitted_at DESC);

CREATE INDEX IF NOT EXISTS ix_user_problems_user_first_solved ON user_problems (user_id, first_solved_at DESC) WHERE first_solved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_reviews_open ON reviews (user_id, scheduled_for) WHERE completed_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_recommendations_active ON recommendations (user_id, score DESC) WHERE expires_at IS NULL AND dismissed_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_user_problems_review_due_open ON user_problems (user_id, review_due_at) WHERE needs_review = true;

CREATE INDEX IF NOT EXISTS ix_ai_insights_lookup ON ai_insights (user_id, type, generated_at DESC);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY profiles_self_select ON profiles
            FOR SELECT TO authenticated USING (id = auth.uid());

CREATE POLICY profiles_self_update ON profiles
            FOR UPDATE TO authenticated
            USING (id = auth.uid()) WITH CHECK (id = auth.uid());

CREATE POLICY profiles_self_insert ON profiles
            FOR INSERT TO authenticated WITH CHECK (id = auth.uid());

ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_settings_owner_all ON user_settings
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE platform_accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY platform_accounts_owner_all ON platform_accounts
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE user_problems ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_problems_owner_all ON user_problems
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY submissions_owner_all ON submissions
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE solving_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY solving_sessions_owner_all ON solving_sessions
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE mistakes ENABLE ROW LEVEL SECURITY;

CREATE POLICY mistakes_owner_all ON mistakes
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE problem_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY problem_notes_owner_all ON problem_notes
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY reviews_owner_all ON reviews
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE user_stats ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_stats_owner_all ON user_stats
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE activity_days ENABLE ROW LEVEL SECURITY;

CREATE POLICY activity_days_owner_all ON activity_days
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE xp_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY xp_transactions_owner_all ON xp_transactions
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE streak_freeze_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY streak_freeze_transactions_owner_all ON streak_freeze_transactions
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE user_achievements ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_achievements_owner_all ON user_achievements
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE daily_goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY daily_goals_owner_all ON daily_goals
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE weekly_goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY weekly_goals_owner_all ON weekly_goals
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE daily_missions ENABLE ROW LEVEL SECURITY;

CREATE POLICY daily_missions_owner_all ON daily_missions
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE contest_participations ENABLE ROW LEVEL SECURITY;

CREATE POLICY contest_participations_owner_all ON contest_participations
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE contest_problem_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY contest_problem_results_owner_all ON contest_problem_results
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;

CREATE POLICY recommendations_owner_all ON recommendations
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE sync_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY sync_runs_owner_all ON sync_runs
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE ai_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY ai_insights_owner_all ON ai_insights
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE ai_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY ai_conversations_owner_all ON ai_conversations
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE ai_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY ai_messages_owner_all ON ai_messages
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE ai_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY ai_usage_owner_all ON ai_usage
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY collections_owner_all ON collections
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE collection_problems ENABLE ROW LEVEL SECURITY;

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
            );

ALTER TABLE resources ENABLE ROW LEVEL SECURITY;

CREATE POLICY resources_read ON resources
                FOR SELECT TO authenticated
                USING (user_id IS NULL OR user_id = auth.uid());

CREATE POLICY resources_write ON resources
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE trusted_channels ENABLE ROW LEVEL SECURITY;

CREATE POLICY trusted_channels_read ON trusted_channels
                FOR SELECT TO authenticated
                USING (user_id IS NULL OR user_id = auth.uid());

CREATE POLICY trusted_channels_write ON trusted_channels
                FOR ALL TO authenticated
                USING (user_id = auth.uid())
                WITH CHECK (user_id = auth.uid());

ALTER TABLE problems ENABLE ROW LEVEL SECURITY;

CREATE POLICY problems_read ON problems
                FOR SELECT TO authenticated USING (true);

ALTER TABLE topics ENABLE ROW LEVEL SECURITY;

CREATE POLICY topics_read ON topics
                FOR SELECT TO authenticated USING (true);

ALTER TABLE patterns ENABLE ROW LEVEL SECURITY;

CREATE POLICY patterns_read ON patterns
                FOR SELECT TO authenticated USING (true);

ALTER TABLE problem_topics ENABLE ROW LEVEL SECURITY;

CREATE POLICY problem_topics_read ON problem_topics
                FOR SELECT TO authenticated USING (true);

ALTER TABLE problem_patterns ENABLE ROW LEVEL SECURITY;

CREATE POLICY problem_patterns_read ON problem_patterns
                FOR SELECT TO authenticated USING (true);

ALTER TABLE sheets ENABLE ROW LEVEL SECURITY;

CREATE POLICY sheets_read ON sheets
                FOR SELECT TO authenticated USING (true);

ALTER TABLE sheet_sections ENABLE ROW LEVEL SECURITY;

CREATE POLICY sheet_sections_read ON sheet_sections
                FOR SELECT TO authenticated USING (true);

ALTER TABLE sheet_problems ENABLE ROW LEVEL SECURITY;

CREATE POLICY sheet_problems_read ON sheet_problems
                FOR SELECT TO authenticated USING (true);

ALTER TABLE achievements ENABLE ROW LEVEL SECURITY;

CREATE POLICY achievements_read ON achievements
                FOR SELECT TO authenticated USING (true);

ALTER TABLE contests ENABLE ROW LEVEL SECURITY;

CREATE POLICY contests_read ON contests
                FOR SELECT TO authenticated USING (true);

ALTER TABLE contest_problems ENABLE ROW LEVEL SECURITY;

CREATE POLICY contest_problems_read ON contest_problems
                FOR SELECT TO authenticated USING (true);

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
        $$;

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
        $$;

UPDATE alembic_version SET version_num='b1f4c2d9e701' WHERE alembic_version.version_num = '3ee3a8277a90';
