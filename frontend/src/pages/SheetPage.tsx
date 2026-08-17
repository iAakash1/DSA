/**
 * One page serves both sheets, driven by slug.
 *
 * CP-31 sections are rating buckets and Striver sections are topics, so the
 * layout adapts from `kind` rather than duplicating the whole screen.
 */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { ProblemTable } from '../components/ProblemTable';
import { Card, Empty, ErrorState, Loading, ProgressBar } from '../components/ui';

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'unsolved', label: 'Unsolved' },
  { value: 'completed', label: 'Solved' },
  { value: 'attempted', label: 'Attempted' },
];

export function SheetPage() {
  const { slug = 'cp31' } = useParams();
  const [section, setSection] = useState<string | null>(null);
  const [status, setStatus] = useState('');

  const detail = useApi(() => api.sheet(slug), [slug]);
  const problems = useApi(
    () => api.sheetProblems(slug, { section: section ?? undefined, status: status || undefined, limit: 400 }),
    [slug, section, status],
  );

  if (detail.loading) return <Loading label="Loading sheet" />;
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  if (!detail.data) return null;

  const sheet = detail.data;
  const isBuckets = sheet.kind === 'cp31';

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div>
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-lg font-semibold">{sheet.name}</h1>
          <span className="tabular text-sm text-ink-dim">
            {sheet.progress.completed}/{sheet.progress.total} · {sheet.progress.percent}%
          </span>
        </div>
        {sheet.description && <p className="mt-1 text-sm text-ink-muted">{sheet.description}</p>}
        <ProgressBar className="mt-3 max-w-md" value={sheet.progress.percent} height="h-2" />

        {sheet.dataset?.state === 'partial' && (
          // Never let a partial corpus read as a completion percentage of the
          // real sheet — say plainly how much of it is actually loaded.
          <p className="mt-2 max-w-xl rounded-lg border border-accent/30 bg-accent-soft/40 px-3 py-2 text-xs text-accent">
            {sheet.dataset.label} — {sheet.dataset.loaded} of {sheet.dataset.expected}{' '}
            problems loaded. Progress below is measured against the loaded subset only.
          </p>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <Card title={isBuckets ? 'Rating buckets' : 'Sections'} className="lg:col-span-1">
          <ul className="max-h-[70vh] space-y-1 overflow-y-auto px-2 py-2">
            <li>
              <button
                onClick={() => setSection(null)}
                className={clsx(
                  'w-full rounded-lg px-2.5 py-1.5 text-left text-sm',
                  section === null ? 'bg-surface-3 text-ink' : 'text-ink-muted hover:bg-surface-2',
                )}
              >
                All sections
              </button>
            </li>
            {sheet.sections.map((item) => {
              const active = section === item.slug;
              return (
                <li key={item.slug}>
                  <button
                    onClick={() => setSection(item.slug)}
                    className={clsx(
                      'w-full rounded-lg px-2.5 py-1.5 text-left',
                      active ? 'bg-surface-3' : 'hover:bg-surface-2',
                    )}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className={clsx('text-sm', active ? 'text-ink' : 'text-ink-muted')}>
                        {item.name}
                      </span>
                      <span className="tabular shrink-0 text-[11px] text-ink-dim">
                        {item.progress.completed}/{item.progress.total}
                      </span>
                    </div>
                    <ProgressBar
                      className="mt-1"
                      height="h-1"
                      value={item.progress.percent}
                      barClass={item.progress.percent === 100 ? 'bg-success' : 'bg-accent'}
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>

        <div className="space-y-3 lg:col-span-3">
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setStatus(filter.value)}
                className={clsx(
                  'btn',
                  status === filter.value ? 'btn-primary' : 'btn-ghost',
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <Card>
            {problems.loading && <Loading />}
            {problems.error && <ErrorState error={problems.error} onRetry={problems.reload} />}
            {problems.data && problems.data.items.length === 0 && (
              <Empty
                title="Nothing here"
                hint={
                  status
                    ? 'Try a different filter.'
                    : 'This sheet has not been imported yet. Run `make seed` or import it from Settings.'
                }
              />
            )}
            {problems.data && problems.data.items.length > 0 && (
              <ProblemTable
                rows={problems.data.items.map((item) => ({ ...item, tags: [] }))}
                showSection={section === null}
                onMarkSolved={async (id) => {
                  await api.solve(id, { solution_source: 'independent' });
                  problems.reload();
                  detail.reload();
                }}
              />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
