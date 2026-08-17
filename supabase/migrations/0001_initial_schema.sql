-- ---------------------------------------------------------------------------
-- GENERATED FILE — DO NOT EDIT BY HAND.
--
-- Produced by: python scripts/generate_supabase_migrations.py
-- Source:      backend/alembic/versions/3ee3a8277a90_initial_schema.py
--
-- To change the schema: add an Alembic revision in backend/alembic/versions,
-- then re-run the generator. Editing this file directly will be overwritten
-- and will desynchronise the ORM models from the database.
-- ---------------------------------------------------------------------------

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 3ee3a8277a90

CREATE TABLE achievements (
    code VARCHAR(64) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    description TEXT NOT NULL, 
    category VARCHAR(32) NOT NULL, 
    icon VARCHAR(32), 
    tier VARCHAR(16) NOT NULL, 
    criteria JSONB NOT NULL, 
    xp_reward INTEGER NOT NULL, 
    sort_order INTEGER NOT NULL, 
    is_hidden BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_achievements PRIMARY KEY (id), 
    CONSTRAINT uq_achievements_code UNIQUE (code)
);

CREATE TABLE contests (
    platform VARCHAR(32) NOT NULL, 
    external_id VARCHAR(64) NOT NULL, 
    name VARCHAR(512) NOT NULL, 
    url TEXT, 
    start_time TIMESTAMP WITH TIME ZONE, 
    duration_seconds INTEGER, 
    contest_type VARCHAR(32), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_contests PRIMARY KEY (id), 
    CONSTRAINT uq_contests_platform_external UNIQUE (platform, external_id)
);

CREATE INDEX ix_contests_platform ON contests (platform);

CREATE INDEX ix_contests_start_time ON contests (start_time);

CREATE TABLE problems (
    platform VARCHAR(32) NOT NULL, 
    external_id VARCHAR(128) NOT NULL, 
    slug VARCHAR(255), 
    title VARCHAR(512) NOT NULL, 
    url TEXT NOT NULL, 
    difficulty VARCHAR(16) NOT NULL, 
    rating INTEGER, 
    rating_source VARCHAR(32), 
    acceptance_rate FLOAT, 
    solved_count INTEGER, 
    contest_id INTEGER, 
    problem_index VARCHAR(8), 
    tags JSONB, 
    extra JSONB, 
    is_premium BOOLEAN NOT NULL, 
    metadata_complete BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_problems PRIMARY KEY (id), 
    CONSTRAINT uq_problems_platform_external_id UNIQUE (platform, external_id)
);

CREATE INDEX ix_problems_contest_id ON problems (contest_id);

CREATE INDEX ix_problems_difficulty ON problems (difficulty);

CREATE INDEX ix_problems_platform ON problems (platform);

CREATE INDEX ix_problems_rating ON problems (rating);

CREATE INDEX ix_problems_slug ON problems (slug);

CREATE TABLE profiles (
    email VARCHAR(320), 
    username VARCHAR(64) NOT NULL, 
    display_name VARCHAR(128), 
    timezone VARCHAR(64) DEFAULT 'UTC' NOT NULL, 
    avatar_url TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_profiles PRIMARY KEY (id)
);

CREATE INDEX ix_profiles_email ON profiles (email);

CREATE TABLE sheets (
    slug VARCHAR(64) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    description TEXT, 
    kind VARCHAR(16) NOT NULL, 
    source_url TEXT, 
    sort_order INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_sheets PRIMARY KEY (id), 
    CONSTRAINT uq_sheets_slug UNIQUE (slug)
);

CREATE TABLE topics (
    slug VARCHAR(128) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    parent_id UUID, 
    kind VARCHAR(16) NOT NULL, 
    description TEXT, 
    sort_order INTEGER NOT NULL, 
    path VARCHAR(512) NOT NULL, 
    depth INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_topics PRIMARY KEY (id), 
    CONSTRAINT fk_topics_parent_id_topics FOREIGN KEY(parent_id) REFERENCES topics (id) ON DELETE SET NULL, 
    CONSTRAINT uq_topics_slug UNIQUE (slug)
);

CREATE INDEX ix_topics_parent_id ON topics (parent_id);

CREATE INDEX ix_topics_path ON topics (path);

CREATE TABLE activity_days (
    user_id UUID NOT NULL, 
    activity_date DATE NOT NULL, 
    problems_solved INTEGER NOT NULL, 
    xp_earned INTEGER NOT NULL, 
    minutes_spent INTEGER NOT NULL, 
    submissions INTEGER NOT NULL, 
    contests INTEGER NOT NULL, 
    upsolves INTEGER NOT NULL, 
    reviews_completed INTEGER NOT NULL, 
    is_frozen BOOLEAN NOT NULL, 
    topics_touched JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_activity_days PRIMARY KEY (id), 
    CONSTRAINT fk_activity_days_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_activity_days_user_date UNIQUE (user_id, activity_date)
);

CREATE INDEX ix_activity_days_user_date ON activity_days (user_id, activity_date);

CREATE INDEX ix_activity_days_user_id ON activity_days (user_id);

CREATE TABLE ai_conversations (
    user_id UUID NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    summary TEXT, 
    archived BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_ai_conversations PRIMARY KEY (id), 
    CONSTRAINT fk_ai_conversations_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_conversations_user_id ON ai_conversations (user_id);

CREATE TABLE ai_insights (
    user_id UUID NOT NULL, 
    type VARCHAR(48) NOT NULL, 
    title VARCHAR(512) NOT NULL, 
    summary TEXT NOT NULL, 
    content TEXT, 
    structured_output JSONB, 
    context_snapshot JSONB, 
    model VARCHAR(128), 
    prompt_version VARCHAR(32) NOT NULL, 
    data_snapshot_hash VARCHAR(64) NOT NULL, 
    confidence VARCHAR(24) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    input_tokens INTEGER, 
    output_tokens INTEGER, 
    latency_ms INTEGER, 
    subject_id UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_ai_insights PRIMARY KEY (id), 
    CONSTRAINT fk_ai_insights_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_insights_snapshot ON ai_insights (user_id, type, data_snapshot_hash);

CREATE INDEX ix_ai_insights_subject_id ON ai_insights (subject_id);

CREATE INDEX ix_ai_insights_user_id ON ai_insights (user_id);

CREATE INDEX ix_ai_insights_user_type_generated ON ai_insights (user_id, type, generated_at);

CREATE TABLE ai_usage (
    user_id UUID NOT NULL, 
    endpoint VARCHAR(64) NOT NULL, 
    model VARCHAR(128) NOT NULL, 
    input_tokens INTEGER NOT NULL, 
    output_tokens INTEGER NOT NULL, 
    latency_ms INTEGER NOT NULL, 
    success BOOLEAN NOT NULL, 
    error TEXT, 
    estimated_cost_usd FLOAT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_ai_usage PRIMARY KEY (id), 
    CONSTRAINT fk_ai_usage_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_usage_user_created ON ai_usage (user_id, created_at);

CREATE INDEX ix_ai_usage_user_id ON ai_usage (user_id);

CREATE TABLE collections (
    user_id UUID NOT NULL, 
    slug VARCHAR(128) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    description TEXT, 
    color VARCHAR(16), 
    icon VARCHAR(32), 
    is_system BOOLEAN NOT NULL, 
    sort_order INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_collections PRIMARY KEY (id), 
    CONSTRAINT fk_collections_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_collections_user_slug UNIQUE (user_id, slug)
);

CREATE INDEX ix_collections_user_id ON collections (user_id);

CREATE TABLE contest_participations (
    user_id UUID NOT NULL, 
    contest_id UUID NOT NULL, 
    rank INTEGER, 
    rating_before INTEGER, 
    rating_after INTEGER, 
    rating_change INTEGER, 
    problems_solved_live INTEGER NOT NULL, 
    problems_upsolved INTEGER NOT NULL, 
    problems_attempted INTEGER NOT NULL, 
    penalty INTEGER, 
    is_virtual BOOLEAN NOT NULL, 
    notes TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_contest_participations PRIMARY KEY (id), 
    CONSTRAINT fk_contest_participations_contest_id_contests FOREIGN KEY(contest_id) REFERENCES contests (id) ON DELETE CASCADE, 
    CONSTRAINT fk_contest_participations_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_contest_participations_user_contest UNIQUE (user_id, contest_id, is_virtual)
);

CREATE INDEX ix_contest_participations_contest_id ON contest_participations (contest_id);

CREATE INDEX ix_contest_participations_user ON contest_participations (user_id);

CREATE INDEX ix_contest_participations_user_id ON contest_participations (user_id);

CREATE TABLE contest_problem_results (
    user_id UUID NOT NULL, 
    contest_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    solved_at TIMESTAMP WITH TIME ZONE, 
    attempts INTEGER NOT NULL, 
    time_from_start_seconds INTEGER, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_contest_problem_results PRIMARY KEY (id), 
    CONSTRAINT fk_contest_problem_results_contest_id_contests FOREIGN KEY(contest_id) REFERENCES contests (id) ON DELETE CASCADE, 
    CONSTRAINT fk_contest_problem_results_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_contest_problem_results_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_contest_problem_results_unique UNIQUE (user_id, contest_id, problem_id)
);

CREATE INDEX ix_contest_problem_results_contest_id ON contest_problem_results (contest_id);

CREATE INDEX ix_contest_problem_results_problem_id ON contest_problem_results (problem_id);

CREATE INDEX ix_contest_problem_results_user_id ON contest_problem_results (user_id);

CREATE TABLE contest_problems (
    contest_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    index VARCHAR(8), 
    points FLOAT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_contest_problems PRIMARY KEY (id), 
    CONSTRAINT fk_contest_problems_contest_id_contests FOREIGN KEY(contest_id) REFERENCES contests (id) ON DELETE CASCADE, 
    CONSTRAINT fk_contest_problems_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT uq_contest_problems_contest_problem UNIQUE (contest_id, problem_id)
);

CREATE INDEX ix_contest_problems_contest_id ON contest_problems (contest_id);

CREATE INDEX ix_contest_problems_problem_id ON contest_problems (problem_id);

CREATE TABLE daily_goals (
    user_id UUID NOT NULL, 
    goal_date DATE NOT NULL, 
    target INTEGER NOT NULL, 
    progress INTEGER NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_daily_goals PRIMARY KEY (id), 
    CONSTRAINT fk_daily_goals_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_daily_goals_user_date UNIQUE (user_id, goal_date)
);

CREATE INDEX ix_daily_goals_user_id ON daily_goals (user_id);

CREATE TABLE daily_missions (
    user_id UUID NOT NULL, 
    mission_date DATE NOT NULL, 
    code VARCHAR(64) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    description TEXT NOT NULL, 
    target INTEGER NOT NULL, 
    progress INTEGER NOT NULL, 
    xp_reward INTEGER NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    params JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_daily_missions PRIMARY KEY (id), 
    CONSTRAINT fk_daily_missions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_daily_missions_user_date_code UNIQUE (user_id, mission_date, code)
);

CREATE INDEX ix_daily_missions_user_id ON daily_missions (user_id);

CREATE TABLE patterns (
    slug VARCHAR(128) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    description TEXT, 
    topic_id UUID, 
    sort_order INTEGER NOT NULL, 
    is_core BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_patterns PRIMARY KEY (id), 
    CONSTRAINT fk_patterns_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE SET NULL, 
    CONSTRAINT uq_patterns_slug UNIQUE (slug)
);

CREATE INDEX ix_patterns_topic_id ON patterns (topic_id);

CREATE TABLE platform_accounts (
    user_id UUID NOT NULL, 
    platform VARCHAR(32) NOT NULL, 
    username VARCHAR(128) NOT NULL, 
    external_id VARCHAR(128), 
    connected BOOLEAN NOT NULL, 
    last_synced_at TIMESTAMP WITH TIME ZONE, 
    last_sync_status VARCHAR(32), 
    last_sync_error TEXT, 
    sync_cursor JSONB, 
    current_rating INTEGER, 
    max_rating INTEGER, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_platform_accounts PRIMARY KEY (id), 
    CONSTRAINT fk_platform_accounts_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_platform_accounts_user_platform UNIQUE (user_id, platform)
);

CREATE INDEX ix_platform_accounts_user_id ON platform_accounts (user_id);

CREATE TABLE problem_notes (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    kind VARCHAR(24) NOT NULL, 
    content_md TEXT NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_problem_notes PRIMARY KEY (id), 
    CONSTRAINT fk_problem_notes_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_problem_notes_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_problem_notes_problem_id ON problem_notes (problem_id);

CREATE INDEX ix_problem_notes_user_id ON problem_notes (user_id);

CREATE INDEX ix_problem_notes_user_problem ON problem_notes (user_id, problem_id);

CREATE TABLE problem_topics (
    problem_id UUID NOT NULL, 
    topic_id UUID NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    is_primary BOOLEAN NOT NULL, 
    CONSTRAINT pk_problem_topics PRIMARY KEY (problem_id, topic_id), 
    CONSTRAINT fk_problem_topics_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_problem_topics_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE CASCADE
);

CREATE TABLE recommendations (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    batch_id VARCHAR(64) NOT NULL, 
    score FLOAT NOT NULL, 
    reason_code VARCHAR(48) NOT NULL, 
    reason_text TEXT NOT NULL, 
    evidence JSONB, 
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    dismissed_at TIMESTAMP WITH TIME ZONE, 
    accepted_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_recommendations PRIMARY KEY (id), 
    CONSTRAINT fk_recommendations_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_recommendations_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_recommendations_user_problem_batch UNIQUE (user_id, problem_id, batch_id)
);

CREATE INDEX ix_recommendations_problem_id ON recommendations (problem_id);

CREATE INDEX ix_recommendations_user_generated ON recommendations (user_id, generated_at);

CREATE INDEX ix_recommendations_user_id ON recommendations (user_id);

CREATE TABLE resources (
    problem_id UUID NOT NULL, 
    user_id UUID, 
    kind VARCHAR(16) NOT NULL, 
    title VARCHAR(512) NOT NULL, 
    url TEXT NOT NULL, 
    provider VARCHAR(32) NOT NULL, 
    external_id VARCHAR(64), 
    channel_id VARCHAR(64), 
    channel_title VARCHAR(255), 
    duration_seconds INTEGER, 
    published_at TIMESTAMP WITH TIME ZONE, 
    thumbnail_url TEXT, 
    score FLOAT NOT NULL, 
    score_breakdown JSONB, 
    is_selected BOOLEAN NOT NULL, 
    is_manual BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_resources PRIMARY KEY (id), 
    CONSTRAINT fk_resources_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_resources_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_resources_problem_url UNIQUE (problem_id, url)
);

CREATE INDEX ix_resources_channel_id ON resources (channel_id);

CREATE INDEX ix_resources_problem_id ON resources (problem_id);

CREATE INDEX ix_resources_user_id ON resources (user_id);

CREATE TABLE reviews (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    reason VARCHAR(32) NOT NULL, 
    reason_detail TEXT, 
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL, 
    interval_days INTEGER NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    outcome VARCHAR(16), 
    evidence JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_reviews PRIMARY KEY (id), 
    CONSTRAINT fk_reviews_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_reviews_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_reviews_problem_id ON reviews (problem_id);

CREATE INDEX ix_reviews_user_id ON reviews (user_id);

CREATE INDEX ix_reviews_user_scheduled ON reviews (user_id, scheduled_for, completed_at);

CREATE TABLE sheet_sections (
    sheet_id UUID NOT NULL, 
    slug VARCHAR(128) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    rating_bucket INTEGER, 
    sort_order INTEGER NOT NULL, 
    topic_id UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_sheet_sections PRIMARY KEY (id), 
    CONSTRAINT fk_sheet_sections_sheet_id_sheets FOREIGN KEY(sheet_id) REFERENCES sheets (id) ON DELETE CASCADE, 
    CONSTRAINT fk_sheet_sections_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE SET NULL, 
    CONSTRAINT uq_sheet_sections_sheet_slug UNIQUE (sheet_id, slug)
);

CREATE INDEX ix_sheet_sections_rating_bucket ON sheet_sections (rating_bucket);

CREATE INDEX ix_sheet_sections_sheet_id ON sheet_sections (sheet_id);

CREATE TABLE solving_sessions (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    time_spent_seconds INTEGER, 
    attempt_count INTEGER NOT NULL, 
    result VARCHAR(16) NOT NULL, 
    solution_source VARCHAR(16) NOT NULL, 
    difficulty_perception INTEGER, 
    confidence INTEGER, 
    approach TEXT, 
    notes TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_solving_sessions PRIMARY KEY (id), 
    CONSTRAINT fk_solving_sessions_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_solving_sessions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_solving_sessions_problem_id ON solving_sessions (problem_id);

CREATE INDEX ix_solving_sessions_user_finished ON solving_sessions (user_id, finished_at);

CREATE INDEX ix_solving_sessions_user_id ON solving_sessions (user_id);

CREATE TABLE streak_freeze_transactions (
    user_id UUID NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    amount INTEGER NOT NULL, 
    xp_cost INTEGER NOT NULL, 
    applies_to_date DATE, 
    balance_after INTEGER NOT NULL, 
    dedupe_key VARCHAR(255) NOT NULL, 
    note TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_streak_freeze_transactions PRIMARY KEY (id), 
    CONSTRAINT fk_streak_freeze_transactions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_streak_freeze_transactions_user_dedupe UNIQUE (user_id, dedupe_key)
);

CREATE INDEX ix_streak_freeze_transactions_user_id ON streak_freeze_transactions (user_id);

CREATE TABLE submissions (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    platform VARCHAR(32) NOT NULL, 
    external_submission_id VARCHAR(64), 
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    verdict VARCHAR(32) NOT NULL, 
    is_accepted BOOLEAN NOT NULL, 
    language VARCHAR(64), 
    runtime_ms INTEGER, 
    memory_kb INTEGER, 
    source VARCHAR(16) NOT NULL, 
    external_contest_id VARCHAR(64), 
    during_contest BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_submissions PRIMARY KEY (id), 
    CONSTRAINT fk_submissions_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_submissions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_submissions_user_platform_external UNIQUE (user_id, platform, external_submission_id)
);

CREATE INDEX ix_submissions_is_accepted ON submissions (is_accepted);

CREATE INDEX ix_submissions_problem_id ON submissions (problem_id);

CREATE INDEX ix_submissions_user_id ON submissions (user_id);

CREATE INDEX ix_submissions_user_problem ON submissions (user_id, problem_id);

CREATE INDEX ix_submissions_user_submitted ON submissions (user_id, submitted_at);

CREATE TABLE sync_runs (
    user_id UUID NOT NULL, 
    platform VARCHAR(32) NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(16) NOT NULL, 
    submissions_fetched INTEGER NOT NULL, 
    submissions_new INTEGER NOT NULL, 
    problems_created INTEGER NOT NULL, 
    problems_solved INTEGER NOT NULL, 
    xp_awarded INTEGER NOT NULL, 
    error TEXT, 
    details JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_sync_runs PRIMARY KEY (id), 
    CONSTRAINT fk_sync_runs_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_sync_runs_user_id ON sync_runs (user_id);

CREATE INDEX ix_sync_runs_user_platform ON sync_runs (user_id, platform, started_at);

CREATE TABLE trusted_channels (
    user_id UUID, 
    channel_id VARCHAR(64) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    weight FLOAT NOT NULL, 
    notes TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_trusted_channels PRIMARY KEY (id), 
    CONSTRAINT fk_trusted_channels_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_trusted_channels_user_channel UNIQUE (user_id, channel_id)
);

CREATE INDEX ix_trusted_channels_user_id ON trusted_channels (user_id);

CREATE TABLE user_achievements (
    user_id UUID NOT NULL, 
    achievement_id UUID NOT NULL, 
    unlocked_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    progress FLOAT NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_user_achievements PRIMARY KEY (id), 
    CONSTRAINT fk_user_achievements_achievement_id_achievements FOREIGN KEY(achievement_id) REFERENCES achievements (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_achievements_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_achievements_user_achievement UNIQUE (user_id, achievement_id)
);

CREATE INDEX ix_user_achievements_achievement_id ON user_achievements (achievement_id);

CREATE INDEX ix_user_achievements_user_id ON user_achievements (user_id);

CREATE TABLE user_problems (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    first_solved_at TIMESTAMP WITH TIME ZONE, 
    last_solved_at TIMESTAMP WITH TIME ZONE, 
    last_attempted_at TIMESTAMP WITH TIME ZONE, 
    attempts INTEGER NOT NULL, 
    solved_count INTEGER NOT NULL, 
    best_solution_source VARCHAR(16), 
    confidence INTEGER, 
    total_time_seconds INTEGER NOT NULL, 
    is_favorite BOOLEAN NOT NULL, 
    needs_review BOOLEAN NOT NULL, 
    review_due_at TIMESTAMP WITH TIME ZONE, 
    review_interval_days INTEGER NOT NULL, 
    review_count INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_user_problems PRIMARY KEY (id), 
    CONSTRAINT fk_user_problems_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_problems_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_problems_user_problem UNIQUE (user_id, problem_id)
);

CREATE INDEX ix_user_problems_problem_id ON user_problems (problem_id);

CREATE INDEX ix_user_problems_review_due ON user_problems (user_id, review_due_at);

CREATE INDEX ix_user_problems_user_id ON user_problems (user_id);

CREATE INDEX ix_user_problems_user_status ON user_problems (user_id, status);

CREATE TABLE user_settings (
    user_id UUID NOT NULL, 
    daily_goal INTEGER DEFAULT 2 NOT NULL, 
    weekly_goal INTEGER DEFAULT (14) NOT NULL, 
    max_freezes INTEGER DEFAULT 3 NOT NULL, 
    freeze_cost_xp INTEGER DEFAULT (500) NOT NULL, 
    auto_apply_freeze BOOLEAN DEFAULT (true) NOT NULL, 
    xp_rules_override JSONB, 
    level_config_override JSONB, 
    streak_qualifying_activities JSONB, 
    ai_daily_insights BOOLEAN DEFAULT (true) NOT NULL, 
    ai_weekly_reviews BOOLEAN DEFAULT (true) NOT NULL, 
    ai_contest_analysis BOOLEAN DEFAULT (true) NOT NULL, 
    ai_recommendations BOOLEAN DEFAULT (true) NOT NULL, 
    ai_coach BOOLEAN DEFAULT (true) NOT NULL, 
    ai_daily_request_budget INTEGER DEFAULT (50) NOT NULL, 
    ai_model_override VARCHAR(128), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_user_settings PRIMARY KEY (user_id), 
    CONSTRAINT fk_user_settings_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE TABLE user_stats (
    user_id UUID NOT NULL, 
    total_xp INTEGER DEFAULT 0 NOT NULL, 
    level INTEGER DEFAULT 1 NOT NULL, 
    current_streak INTEGER DEFAULT 0 NOT NULL, 
    longest_streak INTEGER DEFAULT 0 NOT NULL, 
    last_active_date DATE, 
    available_freezes INTEGER DEFAULT 0 NOT NULL, 
    problems_solved INTEGER DEFAULT 0 NOT NULL, 
    independent_solves INTEGER DEFAULT 0 NOT NULL, 
    last_recomputed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_user_stats PRIMARY KEY (user_id), 
    CONSTRAINT fk_user_stats_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE TABLE weekly_goals (
    user_id UUID NOT NULL, 
    week_start DATE NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    target INTEGER NOT NULL, 
    progress INTEGER NOT NULL, 
    params JSONB, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_weekly_goals PRIMARY KEY (id), 
    CONSTRAINT fk_weekly_goals_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_weekly_goals_user_week_kind UNIQUE (user_id, week_start, kind)
);

CREATE INDEX ix_weekly_goals_user_id ON weekly_goals (user_id);

CREATE TABLE xp_transactions (
    user_id UUID NOT NULL, 
    amount INTEGER NOT NULL, 
    kind VARCHAR(24) NOT NULL, 
    reason VARCHAR(255) NOT NULL, 
    dedupe_key VARCHAR(255) NOT NULL, 
    problem_id UUID, 
    activity_date DATE NOT NULL, 
    awarded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_xp_transactions PRIMARY KEY (id), 
    CONSTRAINT fk_xp_transactions_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE SET NULL, 
    CONSTRAINT fk_xp_transactions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_xp_transactions_user_dedupe UNIQUE (user_id, dedupe_key)
);

CREATE INDEX ix_xp_transactions_user_date ON xp_transactions (user_id, activity_date);

CREATE INDEX ix_xp_transactions_user_id ON xp_transactions (user_id);

CREATE TABLE ai_messages (
    conversation_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(16) NOT NULL, 
    content TEXT NOT NULL, 
    tool_calls JSONB, 
    tokens INTEGER, 
    model VARCHAR(128), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_ai_messages PRIMARY KEY (id), 
    CONSTRAINT fk_ai_messages_conversation_id_ai_conversations FOREIGN KEY(conversation_id) REFERENCES ai_conversations (id) ON DELETE CASCADE, 
    CONSTRAINT fk_ai_messages_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_messages_conversation ON ai_messages (conversation_id, created_at);

CREATE INDEX ix_ai_messages_user_id ON ai_messages (user_id);

CREATE TABLE collection_problems (
    collection_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    note TEXT, 
    position INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_collection_problems PRIMARY KEY (id), 
    CONSTRAINT fk_collection_problems_collection_id_collections FOREIGN KEY(collection_id) REFERENCES collections (id) ON DELETE CASCADE, 
    CONSTRAINT fk_collection_problems_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT uq_collection_problems_collection_problem UNIQUE (collection_id, problem_id)
);

CREATE INDEX ix_collection_problems_collection_id ON collection_problems (collection_id);

CREATE INDEX ix_collection_problems_problem_id ON collection_problems (problem_id);

CREATE TABLE mistakes (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    session_id UUID, 
    mistake_type VARCHAR(48) NOT NULL, 
    note TEXT, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_mistakes PRIMARY KEY (id), 
    CONSTRAINT fk_mistakes_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_mistakes_session_id_solving_sessions FOREIGN KEY(session_id) REFERENCES solving_sessions (id) ON DELETE SET NULL, 
    CONSTRAINT fk_mistakes_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_mistakes_problem_id ON mistakes (problem_id);

CREATE INDEX ix_mistakes_user_id ON mistakes (user_id);

CREATE INDEX ix_mistakes_user_type ON mistakes (user_id, mistake_type);

CREATE TABLE problem_patterns (
    problem_id UUID NOT NULL, 
    pattern_id UUID NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    CONSTRAINT pk_problem_patterns PRIMARY KEY (problem_id, pattern_id), 
    CONSTRAINT fk_problem_patterns_pattern_id_patterns FOREIGN KEY(pattern_id) REFERENCES patterns (id) ON DELETE CASCADE, 
    CONSTRAINT fk_problem_patterns_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE
);

CREATE TABLE sheet_problems (
    sheet_id UUID NOT NULL, 
    section_id UUID, 
    problem_id UUID NOT NULL, 
    order_index INTEGER NOT NULL, 
    label VARCHAR(255), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    CONSTRAINT pk_sheet_problems PRIMARY KEY (id), 
    CONSTRAINT fk_sheet_problems_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_sheet_problems_section_id_sheet_sections FOREIGN KEY(section_id) REFERENCES sheet_sections (id) ON DELETE SET NULL, 
    CONSTRAINT fk_sheet_problems_sheet_id_sheets FOREIGN KEY(sheet_id) REFERENCES sheets (id) ON DELETE CASCADE, 
    CONSTRAINT uq_sheet_problems_sheet_problem UNIQUE (sheet_id, problem_id)
);

CREATE INDEX ix_sheet_problems_problem_id ON sheet_problems (problem_id);

CREATE INDEX ix_sheet_problems_section_id ON sheet_problems (section_id);

CREATE INDEX ix_sheet_problems_sheet_id ON sheet_problems (sheet_id);

INSERT INTO alembic_version (version_num) VALUES ('3ee3a8277a90') RETURNING alembic_version.version_num;
