/** Problem explorer: search, filter, sort, paginate — all server-side. */

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Filter, Search, X } from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { ProblemTable } from '../components/ProblemTable';
import { Card, Empty, ErrorState, Loading, inputBase } from '../components/ui';

const PAGE_SIZE = 50;

const STATUSES = [
  { value: '', label: 'Any status' },
  { value: 'unsolved', label: 'Unsolved' },
  { value: 'attempted', label: 'Attempted' },
  { value: 'completed', label: 'Solved' },
  { value: 'revisit', label: 'Revisit' },
  { value: 'mastered', label: 'Mastered' },
];

const SORTS = [
  { value: 'recently_added', label: 'Recently added' },
  { value: 'rating', label: 'Rating' },
  { value: 'title', label: 'Title' },
  { value: 'recently_solved', label: 'Recently solved' },
  { value: 'time_taken', label: 'Time spent' },
];

export function Problems() {
  const [params, setParams] = useSearchParams();
  const [term, setTerm] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(0);

  // Debounce search so typing does not fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(() => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (term) next.set('q', term);
          else next.delete('q');
          return next;
        },
        { replace: true },
      );
      setPage(0);
    }, 250);
    return () => clearTimeout(handle);
  }, [term, setParams]);

  const filters = useMemo(
    () => ({
      q: params.get('q') ?? undefined,
      platform: params.get('platform') ?? undefined,
      sheet: params.get('sheet') ?? undefined,
      topic: params.get('topic') ?? undefined,
      pattern: params.get('pattern') ?? undefined,
      collection: params.get('collection') ?? undefined,
      status: params.get('status') ?? undefined,
      difficulty: params.get('difficulty') ?? undefined,
      min_rating: params.get('min_rating') ?? undefined,
      max_rating: params.get('max_rating') ?? undefined,
      needs_review: params.get('needs_review') ?? undefined,
      sort: params.get('sort') ?? 'recently_added',
      direction: params.get('direction') ?? 'desc',
    }),
    [params],
  );

  const { data, loading, error, reload } = useApi(
    () => api.problems({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [JSON.stringify(filters), page],
  );

  const topics = useApi(() => api.topics(), []);
  const sheets = useApi(() => api.sheets(), []);

  function setFilter(key: string, value: string) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
    setPage(0);
  }

  const activeFilters = Array.from(params.entries()).filter(
    ([key]) => !['q', 'sort', 'direction'].includes(key),
  );

  async function markSolved(id: string) {
    await api.solve(id, { solution_source: 'independent' });
    reload();
  }

  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Problems</h1>
        <span className="tabular text-sm text-ink-dim">{total.toLocaleString()} total</span>
      </div>

      <Card>
        <div className="space-y-3 px-4 py-3">
          <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2">
            <Search size={15} className="shrink-0 text-ink-dim" />
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Search by title or problem ID…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-ink-dim"
            />
            {term && (
              <button onClick={() => setTerm('')} className="text-ink-dim hover:text-ink">
                <X size={14} />
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <select
              value={filters.platform ?? ''}
              onChange={(e) => setFilter('platform', e.target.value)}
              className={inputBase}
            >
              <option value="">Any platform</option>
              <option value="codeforces">Codeforces</option>
              <option value="leetcode">LeetCode</option>
              <option value="takeuforward">takeUforward</option>
            </select>

            <select
              value={filters.sheet ?? ''}
              onChange={(e) => setFilter('sheet', e.target.value)}
              className={inputBase}
            >
              <option value="">Any sheet</option>
              {(sheets.data ?? []).map((sheet) => (
                <option key={sheet.slug} value={sheet.slug}>
                  {sheet.name}
                </option>
              ))}
            </select>

            <select
              value={filters.topic ?? ''}
              onChange={(e) => setFilter('topic', e.target.value)}
              className={`${inputBase} max-w-48`}
            >
              <option value="">Any topic</option>
              {(topics.data?.items ?? [])
                .filter((t) => t.solved > 0 || t.attempted > 0)
                .map((topic) => (
                  <option key={topic.slug} value={topic.slug}>
                    {topic.name}
                  </option>
                ))}
            </select>

            <select
              value={filters.status ?? ''}
              onChange={(e) => setFilter('status', e.target.value)}
              className={inputBase}
            >
              {STATUSES.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </select>

            <select
              value={filters.difficulty ?? ''}
              onChange={(e) => setFilter('difficulty', e.target.value)}
              className={inputBase}
            >
              <option value="">Any difficulty</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>

            <input
              type="number"
              placeholder="Min rating"
              value={filters.min_rating ?? ''}
              onChange={(e) => setFilter('min_rating', e.target.value)}
              className={`${inputBase} w-28`}
            />
            <input
              type="number"
              placeholder="Max rating"
              value={filters.max_rating ?? ''}
              onChange={(e) => setFilter('max_rating', e.target.value)}
              className={`${inputBase} w-28`}
            />

            <label className="flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked={filters.needs_review === 'true'}
                onChange={(e) => setFilter('needs_review', e.target.checked ? 'true' : '')}
              />
              Needs review
            </label>

            <select
              value={filters.sort}
              onChange={(e) => setFilter('sort', e.target.value)}
              className={`${inputBase} sm:ml-auto`}
            >
              {SORTS.map((sort) => (
                <option key={sort.value} value={sort.value}>
                  Sort: {sort.label}
                </option>
              ))}
            </select>
          </div>

          {activeFilters.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <Filter size={12} className="text-ink-dim" />
              {activeFilters.map(([key, value]) => (
                <button
                  key={key}
                  onClick={() => setFilter(key, '')}
                  className="chip hover:bg-surface-4"
                >
                  {key.replace('_', ' ')}: {value} <X size={10} />
                </button>
              ))}
              <button
                onClick={() => setParams({}, { replace: true })}
                className="text-xs text-ink-dim hover:text-ink"
              >
                clear all
              </button>
            </div>
          )}
        </div>
      </Card>

      <Card>
        {loading && <Loading label="Searching" />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && data.items.length === 0 && (
          <Empty
            title="No problems match these filters"
            hint="Try clearing a filter, or import a sheet from Settings."
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <ProblemTable rows={data.items} onMarkSolved={markSolved} />
            {pages > 1 && (
              <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-sm">
                <span className="text-xs text-ink-dim">
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of{' '}
                  {total.toLocaleString()}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={page === 0}
                    onClick={() => setPage((p) => p - 1)}
                    className="btn btn-ghost disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    disabled={page >= pages - 1}
                    onClick={() => setPage((p) => p + 1)}
                    className="btn btn-ghost disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
