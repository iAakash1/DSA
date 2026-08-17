-- ---------------------------------------------------------------------------
-- GENERATED FILE — DO NOT EDIT BY HAND.
--
-- Produced by: python scripts/generate_supabase_migrations.py
-- Source:      backend/alembic/versions/2392beffef44_sheet_provenance_problem_hints_and_.py
--
-- To change the schema: add an Alembic revision in backend/alembic/versions,
-- then re-run the generator. Editing this file directly will be overwritten
-- and will desynchronise the ORM models from the database.
-- ---------------------------------------------------------------------------

-- Running upgrade b1f4c2d9e701 -> 2392beffef44

ALTER TABLE sheets ADD COLUMN source_metadata JSONB;

ALTER TABLE problems ADD COLUMN hints JSONB;

ALTER TABLE problems ADD COLUMN video_links JSONB;

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

UPDATE alembic_version SET version_num='2392beffef44' WHERE alembic_version.version_num = 'b1f4c2d9e701';
