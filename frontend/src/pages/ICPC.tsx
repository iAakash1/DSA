/**
 * ICPC mode: countdown, evidence-based readiness, roadmap, template library
 * and virtual contests.
 *
 * The rule this page exists to honour: a readiness component with no evidence
 * renders as NOT ENOUGH DATA, never as 0%. The two look nothing alike, because
 * they mean nothing alike.
 */

import { useMemo, useState } from 'react';
import {
  CalendarClock,
  Check,
  ChevronRight,
  ClipboardCopy,
  Flag,
  Info,
  Lock,
  Timer,
  Trophy,
} from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import type {
  Countdown as CountdownData,
  IcpcDashboard,
  IcpcSettings,
  ReadinessComponent,
  RoadmapNode,
  TemplateDetail,
  UpsolveItem,
  VirtualContest as VirtualContestData,
} from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Chip, Empty, ErrorState, Field, Loading, Modal, ProgressBar } from '../components/ui';
import { formatDate, percent } from '../lib/format';

const TABS = ['Overview', 'Roadmap', 'Templates', 'Contests'] as const;
type Tab = (typeof TABS)[number];

const STATE_STYLE: Record<RoadmapNode['state'], string> = {
  comfortable: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  started: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  ready: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  blocked: 'border-line bg-surface-2 text-ink-dim',
};

const STATE_LABEL: Record<RoadmapNode['state'], string> = {
  comfortable: 'Comfortable',
  started: 'Started',
  ready: 'Ready to start',
  blocked: 'Prerequisites first',
};

export function ICPC() {
  const { data, loading, error, reload } = useApi(() => api.icpc(), []);
  const [tab, setTab] = useState<Tab>('Overview');

  if (loading) return <Loading label="Loading ICPC mode" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return <Empty title="ICPC mode unavailable" />;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">ICPC mode</h1>
          <p className="text-xs text-ink-dim">
            {data.settings.team_name
              ? `Team ${data.settings.team_name}`
              : 'Preparation tracked against real solve evidence.'}
          </p>
        </div>
        <Countdown countdown={data.countdown} settings={data.settings} onSaved={reload} />
      </header>

      <nav className="flex gap-1 border-b border-line" role="tablist">
        {TABS.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={clsx(
              'rounded-t px-3 py-2 text-xs font-medium transition-colors',
              tab === name
                ? 'border-b-2 border-accent text-ink'
                : 'text-ink-dim hover:text-ink',
            )}
          >
            {name}
          </button>
        ))}
      </nav>

      {tab === 'Overview' && <Overview data={data} />}
      {tab === 'Roadmap' && <Roadmap onChanged={reload} />}
      {tab === 'Templates' && <Templates />}
      {tab === 'Contests' && <Contests contests={data.recent_contests} upsolve={data.upsolve_queue} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Countdown
// ---------------------------------------------------------------------------

function Countdown({
  countdown,
  settings,
  onSaved,
}: {
  countdown: CountdownData;
  settings: IcpcSettings;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(settings.target_date ?? '');
  const [team, setTeam] = useState(settings.team_name ?? '');
  const [rating, setRating] = useState(settings.target_rating?.toString() ?? '');
  const [days, setDays] = useState(settings.weekly_practice_days.toString());
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setFailure(null);
    try {
      await api.icpcSettings({
        target_date: date || null,
        team_name: team || null,
        target_rating: rating ? Number(rating) : null,
        weekly_practice_days: Number(days),
        enabled: true,
      });
      setOpen(false);
      onSaved();
    } catch (e) {
      setFailure(e instanceof Error ? e.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="card card-hover flex items-center gap-3 px-4 py-2 text-left"
      >
        <CalendarClock size={18} className="text-accent" />
        {countdown.days_remaining === null ? (
          <span className="text-xs text-ink-dim">{countdown.message}</span>
        ) : (
          <span>
            <span className="tabular block text-xl font-semibold text-ink">
              {countdown.days_remaining} days
            </span>
            <span className="text-xs text-ink-dim">
              {countdown.is_past
                ? 'Contest date has passed'
                : `${countdown.weeks_remaining} weeks · ${formatDate(countdown.target_date!)}`}
            </span>
          </span>
        )}
        <ChevronRight size={14} className="text-ink-dim" />
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="ICPC settings">
        <div className="space-y-3 p-4">
          <Field label="Contest date" hint="Drives the countdown. Nothing is assumed until it is set.">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="input w-full"
            />
          </Field>
          <Field label="Team name">
            <input value={team} onChange={(e) => setTeam(e.target.value)} className="input w-full" />
          </Field>
          <Field
            label="Target rating"
            hint="Rating depth is measured against this. Left empty, readiness says it assumed one."
          >
            <input
              type="number"
              min={800}
              max={3500}
              value={rating}
              onChange={(e) => setRating(e.target.value)}
              className="input w-full"
            />
          </Field>
          <Field label="Practice days per week">
            <input
              type="number"
              min={1}
              max={7}
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="input w-full"
            />
          </Field>
          {failure && <p className="text-xs text-rose-400">{failure}</p>}
          <button onClick={save} disabled={saving} className="btn-primary w-full">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function Overview({ data }: { data: IcpcDashboard }) {
  const { readiness, roadmap, upsolve_queue: upsolve } = data;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card
        className="lg:col-span-2"
        title="Readiness"
        subtitle={
          readiness.has_sufficient_data
            ? `Weighted across ${readiness.components_answered} components with evidence`
            : readiness.blocked_reason ?? undefined
        }
      >
        <div className="space-y-4 p-4">
          <div className="flex items-baseline gap-3">
            {readiness.overall === null ? (
              <span className="text-lg font-semibold text-ink-dim">NOT ENOUGH DATA</span>
            ) : (
              <>
                <span className="tabular text-4xl font-semibold text-ink">
                  {percent(readiness.overall)}
                </span>
                <span className="text-xs text-ink-dim">
                  against a target of {readiness.target_rating}
                  {readiness.target_rating_is_default && ' (assumed — set your own)'}
                </span>
              </>
            )}
          </div>

          <div className="space-y-3">
            {readiness.components.map((component) => (
              <ComponentRow key={component.key} component={component} />
            ))}
          </div>
        </div>
      </Card>

      <div className="space-y-4">
        <Card title="Roadmap">
          <div className="space-y-2 p-4 text-xs">
            {(
              [
                ['Comfortable', roadmap.totals.comfortable, 'text-emerald-300'],
                ['Started', roadmap.totals.started, 'text-amber-300'],
                ['Ready to start', roadmap.totals.ready, 'text-sky-300'],
                ['Blocked', roadmap.totals.blocked, 'text-ink-dim'],
              ] as const
            ).map(([label, value, tone]) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-ink-dim">{label}</span>
                <span className={clsx('tabular font-medium', tone)}>
                  {value} / {roadmap.totals.nodes}
                </span>
              </div>
            ))}
            <ProgressBar
              value={roadmap.totals.nodes ? roadmap.totals.comfortable / roadmap.totals.nodes : 0}
              barClass="bg-emerald-500"
            />
          </div>
        </Card>

        <Card title="Upsolve queue" subtitle="Left unsolved in a virtual contest">
          {upsolve.length === 0 ? (
            <Empty title="Nothing to upsolve" hint="Finish a virtual contest to fill this." />
          ) : (
            <ul className="divide-y divide-line">
              {upsolve.map((item) => (
                <li key={`${item.contest_id}-${item.problem_id}`} className="px-4 py-2.5">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-medium text-ink hover:text-accent"
                  >
                    {item.label && <span className="text-ink-dim">{item.label}. </span>}
                    {item.title}
                  </a>
                  <p className="mt-0.5 text-[11px] text-ink-dim">
                    {item.contest_name}
                    {item.wrong_attempts > 0 && ` · ${item.wrong_attempts} wrong attempts`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function ComponentRow({ component }: { component: ReadinessComponent }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const unknown = component.score === null;

  return (
    <div className="rounded border border-line bg-surface-2 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-ink">{component.name}</span>
        <div className="flex items-center gap-2">
          {unknown ? (
            <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-dim">
              Not enough data
            </span>
          ) : (
            <span className="tabular text-xs font-semibold text-ink">
              {percent(component.score)}
            </span>
          )}
          <button
            onClick={() => setShowEvidence((v) => !v)}
            aria-label={`Evidence for ${component.name}`}
            className="text-ink-dim hover:text-ink"
          >
            <Info size={13} />
          </button>
        </div>
      </div>

      {!unknown && <ProgressBar value={component.score!} className="mt-2" />}
      {unknown && component.missing && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-ink-dim">{component.missing}</p>
      )}

      {showEvidence && (
        <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-line pt-2 text-[11px]">
          {Object.entries(component.evidence).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-2">
              <dt className="text-ink-dim">{key.replace(/_/g, ' ')}</dt>
              <dd className="tabular truncate text-ink" title={String(value)}>
                {Array.isArray(value) ? value.length : String(value ?? '—')}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Roadmap
// ---------------------------------------------------------------------------

function Roadmap({ onChanged }: { onChanged: () => void }) {
  const { data, loading, error, reload } = useApi(() => api.icpcRoadmap(), []);

  if (loading) return <Loading label="Loading roadmap" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return <Empty title="No roadmap" />;

  async function mark(node: RoadmapNode) {
    await api.icpcTopic(node.key, { studied: !node.studied });
    reload();
    onChanged();
  }

  return (
    <div className="space-y-4">
      {data.phases.map((phase) => (
        <Card key={phase.key} title={phase.name} subtitle={`${phase.nodes.length} topics`}>
          <ul className="divide-y divide-line">
            {phase.nodes.map((node) => (
              <li key={node.key} className="px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-ink">{node.name}</span>
                      <Chip className={clsx('border', STATE_STYLE[node.state])}>
                        {node.state === 'blocked' && <Lock size={9} className="mr-1 inline" />}
                        {STATE_LABEL[node.state]}
                      </Chip>
                      <span className="tabular text-[11px] text-ink-dim">
                        {node.band[0]}–{node.band[1]}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink-dim">{node.why}</p>
                    {node.unmet_prerequisites.length > 0 && (
                      <p className="mt-1 text-[11px] text-ink-dim">
                        Needs first: {node.unmet_prerequisites.join(', ')}
                      </p>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-3">
                    <span className="tabular text-right text-[11px] text-ink-dim">
                      {node.solved} solved
                      {node.attempted > node.solved && ` · ${node.attempted} attempted`}
                    </span>
                    <button
                      onClick={() => mark(node)}
                      className={clsx(
                        'rounded border px-2 py-1 text-[11px] transition-colors',
                        node.studied
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : 'border-line text-ink-dim hover:text-ink',
                      )}
                    >
                      {node.studied ? <Check size={11} className="mr-1 inline" /> : null}
                      Studied
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

function Templates() {
  const { data, loading, error, reload } = useApi(() => api.icpcTemplates(), []);
  const [openSlug, setOpenSlug] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const out = new Map<string, typeof data>();
    for (const entry of data ?? []) {
      const key = entry.topic.split('.')[0];
      out.set(key, [...(out.get(key) ?? []), entry]);
    }
    return [...out.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [data]);

  if (loading) return <Loading label="Loading templates" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        {grouped.map(([topic, entries]) => (
          <Card key={topic} title={topic.replace(/-/g, ' ')} subtitle={`${entries?.length ?? 0} templates`}>
            <ul className="divide-y divide-line">
              {entries?.map((entry) => (
                <li key={entry.slug}>
                  <button
                    onClick={() => setOpenSlug(entry.slug)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-surface-2"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium text-ink">{entry.name}</span>
                      <span className="text-[11px] text-ink-dim">
                        {entry.complexity} · ~{entry.typing_minutes} min to type
                      </span>
                    </span>
                    <span className="shrink-0">
                      {entry.typed_from_memory ? (
                        <Chip className="border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                          From memory
                        </Chip>
                      ) : entry.reviews > 0 ? (
                        <Chip className="border border-amber-500/30 bg-amber-500/10 text-amber-300">
                          Reviewed
                        </Chip>
                      ) : (
                        <Chip className="border border-line text-ink-dim">Needs review</Chip>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      {openSlug && (
        <TemplateModal slug={openSlug} onClose={() => setOpenSlug(null)} onReviewed={reload} />
      )}
    </>
  );
}

function TemplateModal({
  slug,
  onClose,
  onReviewed,
}: {
  slug: string;
  onClose: () => void;
  onReviewed: () => void;
}) {
  const { data, loading, error } = useApi<TemplateDetail>(() => api.icpcTemplate(slug), [slug]);
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);

  async function copy() {
    if (!data) return;
    await navigator.clipboard.writeText(data.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function review(fromMemory: boolean) {
    setSaving(true);
    try {
      await api.icpcReviewTemplate(slug, { from_memory: fromMemory });
      onReviewed();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={data?.name ?? 'Template'}>
      <div className="max-h-[70vh] space-y-3 overflow-y-auto p-4">
        {loading && <Loading label="Loading template" />}
        {error && <ErrorState error={error} />}
        {data && (
          <>
            <p className="text-xs leading-relaxed text-ink-dim">{data.why}</p>
            <div className="flex flex-wrap gap-2 text-[11px]">
              <Chip className="border border-line text-ink-dim">{data.complexity}</Chip>
              <Chip className="border border-line text-ink-dim">~{data.typing_minutes} min</Chip>
            </div>

            <div className="relative">
              <button
                onClick={copy}
                className="absolute right-2 top-2 rounded border border-line bg-surface px-2 py-1 text-[11px] text-ink-dim hover:text-ink"
              >
                <ClipboardCopy size={11} className="mr-1 inline" />
                {copied ? 'Copied' : 'Copy'}
              </button>
              <pre className="overflow-x-auto rounded border border-line bg-surface-2 p-3 text-[11px] leading-relaxed text-ink">
                <code>{data.code}</code>
              </pre>
            </div>

            {data.pitfalls.length > 0 && (
              <div>
                <h3 className="label mb-1">Pitfalls</h3>
                <ul className="space-y-1 text-[11px] leading-relaxed text-ink-dim">
                  {data.pitfalls.map((pitfall) => (
                    <li key={pitfall} className="flex gap-2">
                      <Flag size={11} className="mt-0.5 shrink-0 text-amber-400" />
                      {pitfall}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex gap-2 border-t border-line pt-3">
              <button onClick={() => review(true)} disabled={saving} className="btn-primary flex-1">
                Typed it from memory
              </button>
              <button onClick={() => review(false)} disabled={saving} className="btn flex-1">
                Read it through
              </button>
            </div>
            {data.reviews.length > 0 && (
              <p className="text-[11px] text-ink-dim">
                Last reviewed {formatDate(data.reviews[0].reviewed_at)} ·{' '}
                {data.reviews.length} recent review{data.reviews.length === 1 ? '' : 's'}
              </p>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Contests
// ---------------------------------------------------------------------------

function Contests({
  contests,
  upsolve,
}: {
  contests: VirtualContestData[];
  upsolve: UpsolveItem[];
}) {
  if (contests.length === 0) {
    return (
      <Empty
        title="No virtual contests yet"
        hint="Contest readiness cannot be inferred from practice solves — run one to measure it."
        icon={<Trophy size={20} />}
      />
    );
  }

  return (
    <div className="space-y-4">
      {contests.map((contest) => (
        <Card
          key={contest.id}
          title={contest.name}
          subtitle={`${formatDate(contest.started_at)} · ${contest.duration_minutes} min`}
          action={
            <span className="flex items-center gap-3 text-xs">
              <span className="tabular text-ink">
                {contest.solved_count}/{contest.problem_count} solved
              </span>
              <span className="tabular flex items-center gap-1 text-ink-dim">
                <Timer size={11} />
                {contest.penalty_minutes} penalty
              </span>
            </span>
          }
        >
          <ul className="divide-y divide-line">
            {contest.problems.map((problem) => (
              <li key={problem.problem_id} className="flex items-center gap-3 px-4 py-2">
                <span className="tabular w-5 text-xs text-ink-dim">{problem.label}</span>
                <a
                  href={problem.url ?? '#'}
                  target="_blank"
                  rel="noreferrer"
                  className="min-w-0 flex-1 truncate text-xs text-ink hover:text-accent"
                >
                  {problem.title}
                </a>
                <span
                  className={clsx(
                    'text-[11px]',
                    problem.status === 'solved'
                      ? 'text-emerald-300'
                      : problem.status === 'upsolved'
                        ? 'text-sky-300'
                        : 'text-ink-dim',
                  )}
                >
                  {problem.status === 'solved' && problem.solved_at_minute !== null
                    ? `${problem.solved_at_minute} min`
                    : problem.status.replace(/_/g, ' ')}
                </span>
                {problem.wrong_attempts > 0 && (
                  <span className="tabular text-[11px] text-rose-400">
                    −{problem.wrong_attempts}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      ))}

      {upsolve.length > 0 && (
        <Card title="Upsolve queue" subtitle={`${upsolve.length} problems left unsolved`}>
          <ul className="divide-y divide-line">
            {upsolve.map((item) => (
              <li key={`${item.contest_id}-${item.problem_id}`} className="px-4 py-2.5">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-ink hover:text-accent"
                >
                  {item.title}
                </a>
                <p className="mt-0.5 text-[11px] text-ink-dim">{item.contest_name}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
