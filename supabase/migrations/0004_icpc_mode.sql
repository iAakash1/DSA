-- ---------------------------------------------------------------------------
-- GENERATED FILE — DO NOT EDIT BY HAND.
--
-- Produced by: python scripts/generate_supabase_migrations.py
-- Source:      backend/alembic/versions/7dbfc979dac3_icpc_mode.py
--
-- To change the schema: add an Alembic revision in backend/alembic/versions,
-- then re-run the generator. Editing this file directly will be overwritten
-- and will desynchronise the ORM models from the database.
-- ---------------------------------------------------------------------------

-- Running upgrade 2392beffef44 -> 7dbfc979dac3

CREATE TABLE icpc_settings (
    user_id UUID NOT NULL, 
    target_date DATE, 
    team_name VARCHAR(128), 
    weekly_practice_days INTEGER NOT NULL, 
    focus_topics JSONB, 
    enabled BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_icpc_settings PRIMARY KEY (user_id), 
    CONSTRAINT fk_icpc_settings_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE TABLE icpc_topic_progress (
    user_id UUID NOT NULL, 
    topic_key VARCHAR(128) NOT NULL, 
    studied BOOLEAN NOT NULL, 
    template_reviewed BOOLEAN NOT NULL, 
    confidence INTEGER, 
    last_practiced_at TIMESTAMP WITH TIME ZONE, 
    notes TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_icpc_topic_progress PRIMARY KEY (id), 
    CONSTRAINT fk_icpc_topic_progress_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_icpc_topic_progress_user_topic UNIQUE (user_id, topic_key)
);

CREATE INDEX ix_icpc_topic_progress_user_id ON icpc_topic_progress (user_id);

CREATE TABLE practice_sessions (
    user_id UUID NOT NULL, 
    target_problems INTEGER NOT NULL, 
    duration_minutes INTEGER NOT NULL, 
    focus_topic VARCHAR(128), 
    min_rating INTEGER, 
    max_rating INTEGER, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(16) NOT NULL, 
    problems_solved INTEGER NOT NULL, 
    problems_attempted INTEGER NOT NULL, 
    hints_used INTEGER NOT NULL, 
    problem_ids JSONB, 
    summary JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_practice_sessions PRIMARY KEY (id), 
    CONSTRAINT fk_practice_sessions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_practice_sessions_user_id ON practice_sessions (user_id);

CREATE INDEX ix_practice_sessions_user_started ON practice_sessions (user_id, started_at);

CREATE TABLE readiness_snapshots (
    user_id UUID NOT NULL, 
    taken_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    overall FLOAT, 
    components JSONB NOT NULL, 
    has_sufficient_data BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_readiness_snapshots PRIMARY KEY (id), 
    CONSTRAINT fk_readiness_snapshots_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_readiness_snapshots_user_id ON readiness_snapshots (user_id);

CREATE INDEX ix_readiness_snapshots_user_taken ON readiness_snapshots (user_id, taken_at);

CREATE TABLE template_reviews (
    user_id UUID NOT NULL, 
    template_slug VARCHAR(64) NOT NULL, 
    reviewed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    from_memory BOOLEAN NOT NULL, 
    seconds_taken INTEGER, 
    confidence INTEGER, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_template_reviews PRIMARY KEY (id), 
    CONSTRAINT fk_template_reviews_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_template_reviews_user_id ON template_reviews (user_id);

CREATE INDEX ix_template_reviews_user_slug ON template_reviews (user_id, template_slug);

CREATE TABLE virtual_contests (
    user_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    duration_minutes INTEGER NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(16) NOT NULL, 
    penalty_minutes INTEGER NOT NULL, 
    notes TEXT, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_virtual_contests PRIMARY KEY (id), 
    CONSTRAINT fk_virtual_contests_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_virtual_contests_user_id ON virtual_contests (user_id);

CREATE INDEX ix_virtual_contests_user_started ON virtual_contests (user_id, started_at);

CREATE TABLE hint_reveals (
    user_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    hint_index INTEGER NOT NULL, 
    revealed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    session_id UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_hint_reveals PRIMARY KEY (id), 
    CONSTRAINT fk_hint_reveals_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT fk_hint_reveals_session_id_practice_sessions FOREIGN KEY(session_id) REFERENCES practice_sessions (id) ON DELETE SET NULL, 
    CONSTRAINT fk_hint_reveals_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_hint_reveals_user_problem_index UNIQUE (user_id, problem_id, hint_index)
);

CREATE INDEX ix_hint_reveals_problem_id ON hint_reveals (problem_id);

CREATE INDEX ix_hint_reveals_user_id ON hint_reveals (user_id);

CREATE TABLE virtual_contest_problems (
    contest_id UUID NOT NULL, 
    problem_id UUID NOT NULL, 
    position INTEGER NOT NULL, 
    label VARCHAR(8), 
    status VARCHAR(16) NOT NULL, 
    wrong_attempts INTEGER NOT NULL, 
    solved_at_minute INTEGER, 
    upsolved_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_virtual_contest_problems PRIMARY KEY (id), 
    CONSTRAINT fk_virtual_contest_problems_contest_id_virtual_contests FOREIGN KEY(contest_id) REFERENCES virtual_contests (id) ON DELETE CASCADE, 
    CONSTRAINT fk_virtual_contest_problems_problem_id_problems FOREIGN KEY(problem_id) REFERENCES problems (id) ON DELETE CASCADE, 
    CONSTRAINT uq_virtual_contest_problems_contest_problem UNIQUE (contest_id, problem_id)
);

CREATE INDEX ix_virtual_contest_problems_contest_id ON virtual_contest_problems (contest_id);

CREATE INDEX ix_virtual_contest_problems_problem_id ON virtual_contest_problems (problem_id);

DO $$
        DECLARE target record;
        BEGIN
            FOR target IN
                SELECT c.table_name FROM information_schema.columns c
                WHERE c.table_schema = 'public' AND c.column_name = 'id'
                  AND c.data_type = 'uuid' AND c.column_default IS NULL
            LOOP
                EXECUTE format(
                    'ALTER TABLE public.%I ALTER COLUMN id SET DEFAULT gen_random_uuid()',
                    target.table_name);
            END LOOP;
        END $$;

UPDATE alembic_version SET version_num='7dbfc979dac3' WHERE alembic_version.version_num = '2392beffef44';
