/** Contest history, rating progression and upsolve tracking. */

import { useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { RefreshCw, Trophy } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Loading, StatTile } from '../components/ui';
import { formatDate, ratingColor, signed } from '../lib/format';

const AXIS = { stroke: '#646d80', fontSize: 11 };

export function Contests() {
  const { data, loading, error, reload } = useApi(() => api.contests(), []);
  const [syncing, setSyncing] = useState(false);

  async function sync() {
    setSyncing(true);
    try {
      await api.syncContests();
      reload();
    } finally {
      setSyncing(false);
    }
  }

  if (loading) return <Loading label="Loading contests" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const summary = data?.summary;
  const items = data?.items ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Contests</h1>
        <button onClick={sync} disabled={syncing} className="btn btn-ghost">
          <RefreshCw size={13} className={clsx(syncing && 'animate-spin')} />
          Import from Codeforces
        </button>
      </div>

      {items.length === 0 ? (
        <Card>
          <Empty
            title="No contest history yet"
            hint="Import your rated Codeforces contests, or add a CodeChef/LeetCode contest manually."
            icon={<Trophy size={22} />}
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatTile label="Contests" value={summary?.count ?? 0} />
            <StatTile
              label="Current rating"
              value={summary?.current_rating ?? '—'}
              accent={ratingColor(summary?.current_rating)}
            />
            <StatTile
              label="Peak rating"
              value={summary?.max_rating ?? '—'}
              accent={ratingColor(summary?.max_rating)}
            />
            <StatTile label="Best rank" value={summary?.best_rank ?? '—'} />
            <StatTile
              label="Upsolves"
              value={summary?.total_upsolves ?? 0}
              hint={`${summary?.average_solved_per_contest ?? 0} avg solved`}
            />
          </div>

          {(summary?.rating_history.length ?? 0) > 1 && (
            <Card title="Rating history">
              <div className="h-64 px-2 py-3">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={summary!.rating_history}>
                    <CartesianGrid stroke="#232936" strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="date"
                      {...AXIS}
                      tickLine={false}
                      tickFormatter={(value) => (value ? formatDate(value).slice(0, 6) : '')}
                    />
                    <YAxis {...AXIS} tickLine={false} domain={['dataMin - 100', 'dataMax + 100']} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#12151c',
                        border: '1px solid #2e3543',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelFormatter={(value) => formatDate(String(value))}
                    />
                    <Line
                      type="monotone"
                      dataKey="rating"
                      stroke="#f5a524"
                      strokeWidth={2}
                      dot={{ r: 2.5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}

          <Card title="History">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left">
                    <th className="px-4 py-2 label">Contest</th>
                    <th className="px-2 py-2 label">Date</th>
                    <th className="px-2 py-2 label">Rank</th>
                    <th className="px-2 py-2 label">Δ</th>
                    <th className="px-2 py-2 label">Rating</th>
                    <th className="px-4 py-2 label">Solved</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((contest) => (
                    <tr key={contest.id} className="border-b border-line/60 hover:bg-surface-2">
                      <td className="px-4 py-2">
                        <div className="max-w-md truncate text-ink">{contest.name}</div>
                        <div className="text-[11px] uppercase text-ink-dim">{contest.platform}</div>
                      </td>
                      <td className="px-2 py-2 text-xs text-ink-dim">{formatDate(contest.date)}</td>
                      <td className="tabular px-2 py-2 text-ink-muted">{contest.rank ?? '—'}</td>
                      <td
                        className={clsx(
                          'tabular px-2 py-2 font-medium',
                          (contest.rating_change ?? 0) > 0
                            ? 'text-success'
                            : (contest.rating_change ?? 0) < 0
                              ? 'text-danger'
                              : 'text-ink-dim',
                        )}
                      >
                        {signed(contest.rating_change)}
                      </td>
                      <td className={clsx('tabular px-2 py-2', ratingColor(contest.rating_after))}>
                        {contest.rating_after ?? '—'}
                      </td>
                      <td className="tabular px-4 py-2 text-xs text-ink-muted">
                        {contest.solved_live} live
                        {contest.upsolved > 0 && (
                          <span className="text-violet"> · {contest.upsolved} upsolved</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
