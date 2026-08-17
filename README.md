# CP-Forge

A competitive programming preparation OS. It unifies Striver's A2Z sheet, CP-31,
and your individual LeetCode/Codeforces problems into one local-first dashboard
that answers the questions a tracker usually can't:

> What am I actually weak at? What should I solve next? Am I improving, or just
> solving more?

Not a streak counter. The point is the analytics engine underneath.

---

## What makes it different

**Mastery is not "problems solved."** A topic's score combines volume,
difficulty, independence, success rate, recency and diversity, then applies a
mistake penalty. Difficulty is weighted above volume on purpose — forty hard
problems must read as stronger than a hundred easy ones.

**It distinguishes two very different weaknesses.** "You haven't practised this
enough" and "you practise this and still fail" need opposite interventions, so
the weakness engine classifies which one you have and shows the evidence.

**Synced solves are marked `unknown`, not `independent`.** Codeforces tells us a
problem was accepted, never whether an editorial was open in the next tab.
Independence rates are computed over self-reported solves only, so the number
means something.

**The AI never computes a statistic.** The deterministic engine owns every
number; Groq only interprets them. Every insight exposes its supporting metrics
behind "Why am I seeing this?", and the app is fully functional with no API key.

**XP cannot be farmed.** The ledger is append-only with a unique dedupe key per
award, so re-solving a problem or re-running a sync is worth exactly zero.

---

## Architecture

```
React (Vite, TS, Tailwind)
        ↓  /api
FastAPI  ──  business logic
        ↓
Analytics engine        ← deterministic source of truth for all statistics
        ↓
Recommendation engine   ← chooses WHICH problems to suggest
        ↓
Supabase PostgreSQL     ← persistent source of truth

        Groq (openai/gpt-oss-120b) ← interprets the metrics, explains the choice
```

The hierarchy matters: the AI is a coaching layer on top of a reliable analytics
system, never the thing computing the truth.

| Layer | Owns |
| --- | --- |
| Supabase PostgreSQL | persistence, RLS |
| FastAPI | business logic, authorization, ~60 endpoints |
| Analytics engine | mastery, weakness, progression — all deterministic |
| Recommendation engine | candidate selection, with machine-readable reasons |
| Groq | natural-language interpretation only |
| React | presentation |

---

## Requirements

- Python 3.12+
- Node 20+
- **A Supabase project.** PostgreSQL is the only supported runtime database.

## Setup

```bash
make install
cp .env.example .env
```

### 1. Database connection

In Supabase: **Project Settings → Database → Connection string → URI**.

```
DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Use the **session pooler on port 5432**, not the transaction pooler on 6543.
The transaction pooler does not support prepared statements, which psycopg
relies on; the session pooler is also IPv4-reachable, which the direct
`db.<ref>.supabase.co` host is not. The scheme is upgraded to `+psycopg`
automatically, so paste the string exactly as Supabase gives it.

There is **no default** for `DATABASE_URL`. Starting without one fails loudly
rather than silently falling back to a local file that looks fine and then
loses your data. SQLite is available for offline work only, and must be opted
into explicitly:

```
DATABASE_URL=sqlite:///./data/cp_forge.db
ALLOW_SQLITE=true
```

`APP_ENV=production` refuses SQLite outright.

### 2. Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | **yes** | Supabase Postgres session-pooler URI |
| `ALLOW_SQLITE` | no | Opt in to SQLite for offline dev/tests |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | no | Project reference; anon key is public by design |
| `SUPABASE_SERVICE_ROLE_KEY` | no | **Backend only.** Never sent to the browser |
| `GROQ_API_KEY` | no | Enables the AI Coach; everything else works without it |
| `GROQ_MODEL` | no | Defaults to `openai/gpt-oss-120b` |
| `YOUTUBE_API_KEY` | no | Trusted-channel editorial search. Backend only |
| `CODEFORCES_HANDLE` / `LEETCODE_USERNAME` | no | Bootstraps accounts; a profile URL is accepted and normalised |
| `AUTH_MODE` | no | `local` (default) or `supabase` |
| `VITE_CLERK_PUBLISHABLE_KEY` | no | Frontend only. Switches auth out of local mode |

Only `VITE_`-prefixed variables reach the browser, and the sole one used is the
Clerk publishable key. The Groq, YouTube and service-role keys are read
server-side exclusively.

### 3. Migrations

```bash
make migrate    # Alembic owns the schema; never create_all()
```

Applies the full chain to whatever `DATABASE_URL` points at. On PostgreSQL this
also installs `pg_trgm`, 30 CHECK constraints, partial/GIN indexes, UUID
defaults, RLS on 40 tables with 44 policies, and the `auth.users` provisioning
trigger. `supabase/migrations/*.sql` is generated from the same chain
(`make migrations-sql`), so the Supabase CLI path and the Alembic path cannot
drift.

### 4. Seed and import

```bash
make seed              # taxonomy, achievements, CP-31, Striver — idempotent
```

Titles, ratings and difficulty come from the Codeforces and LeetCode APIs at
import time; the values in `data/seed/*.json` are only fallbacks. For CP-31 the
authoritative rating also decides the bucket, so the seed file needs nothing but
problem ids. Pass `--offline` to skip network lookups.

### 5. Run

```bash
make dev        # backend :8010, frontend :5173
```

## Verification

```bash
make verify                                    # schema, constraints, RLS coverage, seed
make test                                      # backend + frontend
TEST_DATABASE_URL=postgresql://... \
  backend/.venv/bin/pytest backend/tests/test_rls_postgres.py -v
```

The RLS suite is the important one. It does not read the migration SQL and
conclude it looks correct — it assumes the `authenticated` role with a forged
`auth.uid()` claim, exactly as supabase-js would, and asserts across all 25
user-owned tables that one user cannot SELECT, INSERT, UPDATE or DELETE
another's rows. **It skips loudly rather than passing when no PostgreSQL URL is
supplied**, so a green run without that variable proves nothing about RLS.

## Deployment

- Set `APP_ENV=production`, a PostgreSQL `DATABASE_URL`, and `AUTH_MODE=supabase`.
- Set `SCHEDULER_ENABLED=true` on exactly one instance — APScheduler is
  in-process, so running it on several would duplicate syncs.
- Serve `frontend/dist` as static files; point the `/api` proxy at the backend.
- `make backup` before every migration.

---

## How the pieces work

### Canonical problems

`(platform, external_id)` is the unique identity. `1400B`, `1400/B` and the full
Codeforces URL all collapse to one row. A problem appearing in CP-31, a
collection and a contest is **one problem with three memberships** — never three
rows.

### Imports

Sheets import from JSON (`data/seed/`). Metadata in the file is a *hint*: when
the platform archive is reachable it wins, because it is authoritative. For
CP-31 the authoritative rating also decides the bucket, so the file only needs
problem ids — no hand-maintained rating table to drift. Imports are idempotent
and report `Imported / Updated / Skipped / Duplicates merged / Errors`.

### Streaks

Days are bucketed in **your** timezone, never UTC. Today is never counted as
missed. A freeze only saves a streak when one is actually consumed, and every
movement is a recorded transaction — history is never silently rewritten. A gap
larger than your freeze balance is left unprotected rather than partially spent.

### Platform sync

Official APIs only, no scraping. Codeforces is throttled to one request per two
seconds. Re-running a sync is free of side effects: submissions are deduped by
platform id, so nothing double-counts.

**LeetCode limitation, stated honestly:** the public GraphQL API exposes only
the ~20 most recent accepted submissions. It is a rolling window, not a history,
so a first sync cannot reconstruct years of solves. Sync regularly, or backfill
from an export.

### Offline behaviour

Every external dependency can fail without breaking the app. Codeforces down?
Existing data is untouched and the error names the last successful sync. No Groq
key? Insights fall back to deterministic analytics, clearly labelled. No YouTube
key? The problem page says so instead of showing random videos.

---

## Testing

```bash
make test-backend      # 79 tests
```

Tests run against the real migration chain, not `create_all`, so they exercise
the schema that ships. They cover the invariants that matter: XP dedup, streak
and timezone boundaries, freeze accounting, problem normalization, import
idempotency, cross-user isolation, AI tool scoping, and structured-output
validation.

Two bugs these tests caught, both now regression-locked:

- A duplicate daily-bonus insert called `db.rollback()`, discarding the entire
  in-flight transaction — so the third solve of a day was silently lost. Each
  award now runs in its own savepoint.
- Mission progress advanced on re-solves, so "solve 2 problems" could be cleared
  by solving one problem twice. Missions now count first solves only.

---

## Project layout

```
backend/app/
  analytics/        mastery, weakness, stats, activity — the truth layer
  recommendations/  deterministic candidate selection
  gamification/     XP ledger, levels, streaks, freezes, achievements
  integrations/     Codeforces, LeetCode, YouTube adapters
  ai/               provider abstraction, context builder, prompts, tools
  services/         business logic
  api/routes/       ~60 endpoints
frontend/src/
  pages/ components/ hooks/ lib/
scripts/            seed, import, sync, backup, verify, migration generation
supabase/migrations/  generated SQL — do not hand-edit
docs/
```

## Authentication

Identity lives behind `frontend/src/lib/auth.ts`. No provider SDK is imported
anywhere else, so switching to Clerk means implementing `setTokenProvider` in
that one file. Until a provider is configured the app runs in local single-user
mode — the backend still derives the user id itself and never trusts one sent by
the client.

## Troubleshooting

**Port already in use** — the backend defaults to 8010; override the frontend
proxy with `VITE_API_TARGET`.

**"database schema is out of date"** — run `make migrate`.

**Sheets look empty** — run `make seed`. Run it without `--offline` so titles
and ratings are fetched from the platforms.

**AI Coach unavailable** — expected without `GROQ_API_KEY`. Every other feature
continues to work.
