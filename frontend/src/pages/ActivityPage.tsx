/** Full-page activity heatmap and day drill-down. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type HeatmapDay } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Heatmap } from '../components/Heatmap';
import { Card, Empty, ErrorState, Loading, StatTile } from '../components/ui';
import { formatDate, percent, ratingColor } from '../lib/format';

export function ActivityPage() {
  const { data, loading, error, reload } = useApi(() => api.heatmap(), []);
  const [selected, setSelected] = useState<HeatmapDay | null>(null);
  const detail = useApi(
    () => (selected ? api.activityDay(selected.date) : Promise.resolve(null)),
    [selected?.date],
  );

  if (loading) return <Loading label="Loading activity" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <h1 className="text-lg font-semibold">Activity</h1>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Problems" value={data.totals.problems} hint="last 365 days" />
        <StatTile label="Active days" value={data.totals.active_days} />
        <StatTile label="Coverage" value={percent(data.totals.coverage)} hint="of the year" />
        <StatTile label="XP earned" value={data.totals.xp.toLocaleString()} />
      </div>

      <Card title="365-day activity" subtitle="Bucketed in your configured timezone">
        <div className="px-4 py-4">
          <Heatmap days={data.days} onSelect={setSelected} />
        </div>
      </Card>

      {selected && (
        <Card title={formatDate(selected.date)} action={
          <button onClick={() => setSelected(null)} className="text-xs text-ink-dim hover:text-ink">
            Close
          </button>
        }>
          {detail.loading && <Loading />}
          {detail.data && (
            <div className="px-4 py-4">
              <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
                {[
                  ['Solved', detail.data.problems.length],
                  ['XP', detail.data.xp],
                  ['Minutes', detail.data.minutes],
                  ['Submissions', detail.data.submissions],
                  ['Reviews', detail.data.reviews],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <div className="label">{label}</div>
                    <div className="tabular text-lg font-semibold">{value}</div>
                  </div>
                ))}
              </div>

              {detail.data.topics.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {detail.data.topics.map((topic) => (
                    <span key={topic} className="chip">
                      {topic}
                    </span>
                  ))}
                </div>
              )}

              {detail.data.problems.length === 0 ? (
                <Empty title="No problems solved on this day" />
              ) : (
                <ul className="divide-y divide-line">
                  {detail.data.problems.map((problem) => (
                    <li key={problem.id} className="flex items-center justify-between py-2">
                      <Link to={`/problems/${problem.id}`} className="truncate text-sm hover:text-accent">
                        {problem.title}
                      </Link>
                      <span className={`shrink-0 font-mono text-xs ${ratingColor(problem.rating)}`}>
                        {problem.rating ?? '—'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
