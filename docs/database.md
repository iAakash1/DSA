# Database

Supabase PostgreSQL in production, SQLite for tests and offline development.
One set of SQLAlchemy models and one migration chain serve both.

## Ownership rules

1. **Schema is owned by migrations.** The application never calls
   `create_all()`. `app/db/bootstrap.py` verifies at startup that the database
   is reachable and at head, and logs the exact fix if it is not.
2. **`backend/alembic/versions/` is the source of truth.**
   `supabase/migrations/*.sql` is *generated* from it by
   `scripts/generate_supabase_migrations.py`. Never hand-edit the SQL — it will
   be overwritten and the ORM will silently disagree with the database.
3. **Derived data is always rebuildable.** `user_stats`, `activity_days` and
   `user_problems` are caches over the immutable ledgers (`submissions`,
   `xp_transactions`, `solving_sessions`). `recompute_user_state()` rebuilds
   all of them from scratch.

## Applying migrations

```bash
# Direct connection (works for Supabase and local Postgres)
cd backend && alembic upgrade head

# Or via the Supabase CLI, using the generated SQL
supabase link --project-ref <your-ref>
supabase db push
```

After a schema change:

```bash
make migration m="add contest notes"   # autogenerate + regenerate SQL
make migrations-sql                    # regenerate SQL only
```

CI can assert the two are in sync:

```bash
python scripts/generate_supabase_migrations.py --check
```

## Verifying

```bash
make verify
```

On PostgreSQL this checks schema, constraints, indexes, RLS coverage, and then
actually assumes the `authenticated` role with a forged JWT claim to prove one
user cannot read another's rows. On SQLite the Postgres-only checks are
skipped and reported as skipped rather than silently passing.

## Migration chain

| Revision       | Contents |
| -------------- | -------- |
| `initial schema` | 40 tables, foreign keys, unique constraints, base indexes, server-side defaults |
| `rls_constraints_indexes` | `pg_trgm`, UUID defaults, 30 CHECK constraints, partial/GIN indexes, RLS + 44 policies, `auth.users` provisioning trigger |

The second migration is a no-op on SQLite, which has no row-level security.

## Row-level security

RLS is enabled on all 29 user-scoped tables plus the shared catalog tables.

- **User-owned tables** (`submissions`, `xp_transactions`, `ai_insights`, …)
  use `USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())`.
- **`collection_problems`** has no `user_id`; ownership flows through an
  `EXISTS` check against the parent collection.
- **`resources` / `trusted_channels`** have a nullable `user_id`. `NULL` rows
  are global defaults readable by everyone; writes require ownership.
- **Catalog tables** (`problems`, `topics`, `sheets`, `achievements`, …) are
  readable by any authenticated user and writable only by the backend.

> **Important:** the FastAPI backend connects with a privileged role that
> **bypasses RLS by design**. Authorization is enforced in application code —
> every query is scoped by the profile id derived from the verified JWT, and a
> user id supplied by the client is never trusted. RLS is defence in depth for
> direct `supabase-js` access from the browser. Both layers exist on purpose;
> neither is a substitute for the other.

New Supabase auth users are provisioned by the `on_auth_user_created` trigger,
which inserts `profiles`, `user_settings` and `user_stats`. The trigger is
guarded so the migration still applies to a plain Postgres instance with no
`auth` schema.

## Why server-side defaults

Every NOT NULL column with a default carries a real DDL `DEFAULT`. SQLAlchemy's
Python-side defaults do not run for rows inserted by a database trigger or by
`supabase-js`, so without them the provisioning trigger would violate NOT NULL.
`gen_random_uuid()` is the exception — it is Postgres-only and is therefore
applied in the Postgres-only migration rather than on the models.

## Core tables

**Identity** — `profiles` (mirrors `auth.users.id`), `user_settings`,
`platform_accounts`.

**Problems** — `problems` is canonical, unique on `(platform, external_id)`.
A problem appearing in CP-31, a collection and a contest is *one* row with
three memberships. `topics` is a self-referencing hierarchy with a
materialized `path` so a Dijkstra solve rolls up to Shortest Path and Graphs
without a recursive CTE. `patterns` is a deliberately separate axis.

**Sheets** — `sheets` → `sheet_sections` → `sheet_problems`. Striver sections
are topics; CP-31 sections are rating buckets.

**Progress** — `submissions` (immutable history), `solving_sessions`
(self-reported time/confidence/independence), `mistakes`, `problem_notes`,
`reviews`. `user_problems` is the derived per-user cache.

**Gamification** — `xp_transactions` is an append-only ledger with a unique
`(user_id, dedupe_key)`. That index is the entire anti-exploit mechanism:
re-solving a problem or re-running a sync computes the same key and the second
insert simply fails. Balances are derived, never edited.
`streak_freeze_transactions` records every freeze movement, so a protected day
is auditable rather than a silent history rewrite.

**AI** — `ai_insights` caches generated insights against a
`data_snapshot_hash` of the deterministic metrics that produced them, so
unchanged data costs zero tokens.

## Import format

Sheets are imported from JSON. See `data/seed/cp31.json` and
`data/seed/striver_a2z.json`.

```json
{
  "sheet":    { "slug": "cp31", "name": "CP-31", "kind": "cp31" },
  "sections": [ { "slug": "800", "name": "800", "kind": "rating_bucket", "rating_bucket": 800 } ],
  "problems": [ { "platform": "codeforces", "external_id": "4A", "section": "800" } ]
}
```

Metadata in the file is a *hint*. When the platform archive is reachable it
wins, because it is authoritative and current. For rating-bucketed sheets the
authoritative rating also decides the bucket, so the file only needs problem
ids — no hand-maintained rating table to drift.

Imports are idempotent and report what happened:

```
Imported: 61  Updated: 0  Skipped: 0  Duplicates merged: 0  Errors: 0
```

## Backups

```bash
make backup
```

`pg_dump` for PostgreSQL, SQLite's online backup API otherwise (safe while the
app is writing). Output lands in `data/backups/`.
