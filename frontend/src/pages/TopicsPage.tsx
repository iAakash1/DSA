/** Topic and pattern mastery, with the weakness engine's evidence. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import { api, type Mastery } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Loading, ProgressBar } from '../components/ui';
import { masteryColor, percent, severityColor } from '../lib/format';

export function TopicsPage() {
  const [tab, setTab] = useState<'topics' | 'patterns'>('topics');
  const topics = useApi(() => api.topics(), []);
  const patterns = useApi(() => api.patterns(), []);
  const weaknesses = useApi(() => api.weaknesses(), []);

  const active = tab === 'topics' ? topics : patterns;
  const items: Mastery[] =
    tab === 'topics' ? (topics.data?.items ?? []) : (patterns.data?.items ?? []);

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Mastery</h1>
        <div className="flex gap-1.5">
          {(['topics', 'patterns'] as const).map((value) => (
            <button
              key={value}
              onClick={() => setTab(value)}
              className={clsx('btn', tab === value ? 'btn-primary' : 'btn-ghost')}
            >
              {value === 'topics' ? 'Topics' : 'Patterns'}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card
            title={tab === 'topics' ? 'Topic mastery' : 'Pattern mastery'}
            subtitle="Volume, difficulty, independence, success, recency and mistakes combined"
          >
            {active.loading && <Loading />}
            {active.error && <ErrorState error={active.error} onRetry={active.reload} />}
            {!active.loading && items.length === 0 && (
              <Empty
                title="No mastery data yet"
                hint="Solve problems across a few topics and this fills in."
              />
            )}
            {items.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-left">
                      <th className="px-4 py-2 label">Name</th>
                      <th className="px-2 py-2 label">Solved</th>
                      <th className="px-2 py-2 label">Success</th>
                      <th className="px-2 py-2 label">Avg rating</th>
                      <th className="px-2 py-2 label">Last</th>
                      <th className="w-40 px-4 py-2 label">Mastery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.slice(0, 40).map((item) => (
                      <tr key={item.slug} className="border-b border-line/60 hover:bg-surface-2">
                        <td className="px-4 py-2">
                          <Link
                            to={`/problems?${tab === 'topics' ? 'topic' : 'pattern'}=${item.slug}`}
                            className="font-medium text-ink hover:text-accent"
                          >
                            {item.name}
                          </Link>
                          <div className="text-[11px] text-ink-dim">
                            {item.confidence.replace('_', ' ')}
                          </div>
                        </td>
                        <td className="tabular px-2 py-2 text-ink-muted">{item.solved}</td>
                        <td className="tabular px-2 py-2 text-ink-muted">
                          {percent(item.success_rate)}
                        </td>
                        <td className="tabular px-2 py-2 text-ink-muted">
                          {item.avg_rating ?? '—'}
                        </td>
                        <td className="px-2 py-2 text-xs text-ink-dim">
                          {item.days_since_practice === null
                            ? '—'
                            : item.days_since_practice === 0
                              ? 'today'
                              : `${item.days_since_practice}d`}
                        </td>
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-2">
                            <ProgressBar
                              value={item.mastery}
                              className="flex-1"
                              barClass={
                                item.mastery >= 61
                                  ? 'bg-success'
                                  : item.mastery >= 41
                                    ? 'bg-accent'
                                    : 'bg-danger'
                              }
                            />
                            <span className={clsx('tabular w-9 text-right text-xs', masteryColor(item.mastery))}>
                              {item.mastery.toFixed(0)}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Weaknesses" subtitle="Ranked by combined signal strength">
            {weaknesses.loading && <Loading />}
            {weaknesses.data?.weaknesses.length === 0 && (
              <Empty
                title="No weaknesses detected"
                hint={
                  weaknesses.data?.has_enough_data
                    ? 'Nothing is showing multiple weakness signals right now.'
                    : 'Not enough data yet to judge — keep solving.'
                }
              />
            )}
            <ul className="divide-y divide-line">
              {(weaknesses.data?.weaknesses ?? []).map((weakness) => (
                <li key={`${weakness.kind}-${weakness.slug}`} className="px-4 py-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium text-ink">{weakness.name}</span>
                    <span className={clsx('text-[11px] uppercase', severityColor(weakness.severity))}>
                      {weakness.severity}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-accent">{weakness.root_cause_label}</div>
                  <ul className="mt-1.5 space-y-0.5">
                    {weakness.evidence.slice(0, 3).map((item, i) => (
                      <li key={i} className="text-xs text-ink-dim">
                        · {item.description}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                    {weakness.recommended_action}
                  </p>
                </li>
              ))}
            </ul>
          </Card>

          {(weaknesses.data?.strongest_topics.length ?? 0) > 0 && (
            <Card title="Strongest">
              <ul className="divide-y divide-line">
                {weaknesses.data!.strongest_topics.map((topic) => (
                  <li key={topic.slug} className="flex items-center justify-between px-4 py-2">
                    <span className="text-sm text-ink-muted">{topic.name}</span>
                    <span className={clsx('tabular text-xs', masteryColor(topic.mastery))}>
                      {topic.mastery.toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {(topics.data?.untouched.length ?? 0) > 0 && (
            <Card title="Never practised" subtitle="Topics with no recorded activity">
              <div className="flex flex-wrap gap-1.5 px-4 py-3">
                {topics.data!.untouched.map((topic) => (
                  <Link key={topic.slug} to={`/problems?topic=${topic.slug}`} className="chip hover:bg-surface-4">
                    {topic.name}
                  </Link>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
