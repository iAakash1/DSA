/** Today's missions and the deterministic recommendation queue. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Loading, ProgressBar } from '../components/ui';
import { problemRef, ratingColor } from '../lib/format';

export function Missions() {
  const missions = useApi(() => api.missions(), []);
  const recommendations = useApi(() => api.recommendations(), []);
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    setRefreshing(true);
    try {
      await api.refreshRecommendations();
      recommendations.reload();
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h1 className="text-lg font-semibold">Practice</h1>

      <Card title="Today's mission" subtitle="Generated from your actual data, not a random list">
        {missions.loading && <Loading />}
        {missions.error && <ErrorState error={missions.error} onRetry={missions.reload} />}
        {missions.data?.length === 0 && <Empty title="No missions generated yet" />}
        <ul className="divide-y divide-line">
          {(missions.data ?? []).map((mission) => (
            <li key={mission.id} className="flex items-start gap-3 px-4 py-3">
              <span
                className={clsx(
                  'mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border',
                  mission.completed ? 'border-success bg-success text-surface-0' : 'border-line-strong',
                )}
              >
                {mission.completed && <Check size={12} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span
                    className={clsx(
                      'font-medium',
                      mission.completed ? 'text-ink-dim line-through' : 'text-ink',
                    )}
                  >
                    {mission.title}
                  </span>
                  <span className="tabular shrink-0 text-xs text-ink-dim">
                    {mission.progress}/{mission.target} · +{mission.xp_reward} XP
                  </span>
                </div>
                <p className="mt-0.5 text-sm text-ink-muted">{mission.description}</p>
                <ProgressBar
                  className="mt-2"
                  value={(mission.progress / Math.max(1, mission.target)) * 100}
                  barClass={mission.completed ? 'bg-success' : 'bg-accent'}
                />
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card
        title="Recommended problems"
        subtitle="Selected by the deterministic engine — every one carries its reason"
        action={
          <button onClick={refresh} disabled={refreshing} className="btn btn-ghost">
            <RefreshCw size={13} className={clsx(refreshing && 'animate-spin')} />
            Refresh
          </button>
        }
      >
        {recommendations.loading && <Loading />}
        {recommendations.error && (
          <ErrorState error={recommendations.error} onRetry={recommendations.reload} />
        )}
        {recommendations.data?.length === 0 && (
          <Empty
            title="No recommendations yet"
            hint="Solve a few problems and we'll build your personalized queue."
          />
        )}
        <ul className="divide-y divide-line">
          {(recommendations.data ?? []).map((rec) => (
            <li key={rec.problem_id} className="px-4 py-3.5 hover:bg-surface-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link
                    to={`/problems/${rec.problem_id}`}
                    className="font-medium text-ink hover:text-accent"
                  >
                    {rec.problem.title}
                  </Link>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 font-mono text-[11px] text-ink-dim">
                    <span>
                      {problemRef(rec.problem)}
                    </span>
                    {rec.problem.rating && (
                      <span className={ratingColor(rec.problem.rating)}>{rec.problem.rating}</span>
                    )}
                    <span className="text-accent">+{rec.expected_xp} XP</span>
                    <span className="chip">{rec.reason_code.replace(/_/g, ' ')}</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">{rec.reason_text}</p>
                  {Object.keys(rec.evidence ?? {}).length > 0 && (
                    <details className="mt-1.5">
                      <summary className="cursor-pointer text-xs text-ink-dim hover:text-ink-muted">
                        Why this problem?
                      </summary>
                      <dl className="mt-1.5 grid gap-1 sm:grid-cols-2">
                        {Object.entries(rec.evidence).map(([key, value]) => (
                          <div key={key} className="rounded bg-surface-2 px-2 py-1">
                            <dt className="font-mono text-[10px] text-ink-dim">{key}</dt>
                            <dd className="text-xs text-ink">{String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  )}
                </div>
                <a
                  href={rec.problem.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="btn btn-primary shrink-0"
                >
                  Solve <ArrowUpRight size={13} />
                </a>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
