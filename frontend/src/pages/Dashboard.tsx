/** The home screen: what happened, what's weak, what to do next. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, Flame, Target, TrendingUp, Zap } from 'lucide-react';
import clsx from 'clsx';
import { api, type HeatmapDay } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { AICoachCard } from '../components/AICoachCard';
import { Heatmap } from '../components/Heatmap';
import { Card, Empty, ErrorState, Loading, Modal, ProgressBar, StatTile } from '../components/ui';
import {
  formatDate,
  masteryColor,
  problemRef,
  ratingColor,
  relativeDate,
  severityColor,
  signed,
} from '../lib/format';

export function Dashboard() {
  const { data, loading, error, reload } = useApi(() => api.dashboard(), []);
  const ai = useApi(() => api.aiDaily(), []);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedDay, setSelectedDay] = useState<HeatmapDay | null>(null);

  async function refreshInsight() {
    setRefreshing(true);
    try {
      await api.aiDaily(true);
      ai.reload();
    } finally {
      setRefreshing(false);
    }
  }

  if (loading) return <Loading label="Loading your dashboard" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const { streak, level, daily_goal, totals, difficulty, volume } = data;

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <StatTile
          label="Streak"
          value={streak.current}
          hint={`longest ${streak.longest}`}
          accent={streak.active_today ? 'text-accent' : undefined}
          icon={<Flame size={14} />}
        />
        <StatTile label="Level" value={level.level} hint={level.rank} icon={<TrendingUp size={14} />} />
        <StatTile
          label="XP"
          value={level.total_xp.toLocaleString()}
          hint={level.xp_to_next_level ? `${level.xp_to_next_level} to next` : 'max level'}
          icon={<Zap size={14} />}
        />
        <StatTile
          label="Solved"
          value={totals.problems_solved}
          hint={`${volume.solved_last_30_days ?? 0} in 30d`}
        />
        <StatTile
          label="Avg rating"
          value={difficulty.average_cf_rating ?? '—'}
          hint={
            difficulty.rating_change_30d
              ? `${signed(difficulty.rating_change_30d)} vs prev 30d`
              : `max ${difficulty.highest_cf_rating ?? '—'}`
          }
          accent={ratingColor(difficulty.average_cf_rating)}
        />
        <StatTile
          label="Daily goal"
          value={`${daily_goal.progress}/${daily_goal.target}`}
          hint={daily_goal.completed ? 'complete' : 'in progress'}
          accent={daily_goal.completed ? 'text-success' : undefined}
          icon={<Target size={14} />}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <AICoachCard
            insight={ai.data}
            loading={ai.loading}
            onRefresh={refreshInsight}
            refreshing={refreshing}
          />

          <Card title="Recommended next" subtitle="Chosen from your weakest areas and current level">
            {data.recommendations.length === 0 ? (
              <Empty
                title="No recommendations yet"
                hint="Import a sheet or sync a platform account and they will appear here."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.recommendations.map((rec) => (
                  <li key={rec.problem_id} className="px-4 py-3 hover:bg-surface-2">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link
                          to={`/problems/${rec.problem_id}`}
                          className="font-medium text-ink hover:text-accent"
                        >
                          {rec.problem.title}
                        </Link>
                        <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-ink-dim">
                          <span>
                            {problemRef(rec.problem)}
                          </span>
                          {rec.problem.rating && (
                            <span className={ratingColor(rec.problem.rating)}>{rec.problem.rating}</span>
                          )}
                          <span className="text-accent">+{rec.expected_xp} XP</span>
                        </div>
                        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                          {rec.reason_text}
                        </p>
                      </div>
                      <a
                        href={rec.problem.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="btn btn-ghost shrink-0"
                      >
                        Solve <ArrowUpRight size={13} />
                      </a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Activity"
            subtitle={`${data.heatmap.totals.problems} problems over ${data.heatmap.totals.active_days} active days`}
          >
            <div className="px-4 py-4">
              <Heatmap days={data.heatmap.days} onSelect={setSelectedDay} />
            </div>
          </Card>

          <Card title="Recent activity">
            {data.recent_activity.length === 0 ? (
              <Empty title="Nothing solved yet" hint="Solve a problem or run a sync to populate this." />
            ) : (
              <ul className="divide-y divide-line">
                {data.recent_activity.map((item) => (
                  <li key={item.problem_id} className="flex items-center justify-between gap-3 px-4 py-2">
                    <Link
                      to={`/problems/${item.problem_id}`}
                      className="min-w-0 truncate text-sm text-ink hover:text-accent"
                    >
                      {item.title}
                    </Link>
                    <div className="flex shrink-0 items-center gap-3 font-mono text-[11px] text-ink-dim">
                      {item.rating && <span className={ratingColor(item.rating)}>{item.rating}</span>}
                      <span>{relativeDate(item.solved_at)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card title="Today's mission">
            {data.missions.length === 0 ? (
              <Empty title="No missions yet" />
            ) : (
              <ul className="divide-y divide-line">
                {data.missions.map((mission) => (
                  <li key={mission.id} className="px-4 py-3">
                    <div className="flex items-start gap-2">
                      <span
                        className={clsx(
                          'mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border',
                          mission.completed
                            ? 'border-success bg-success text-surface-0'
                            : 'border-line-strong',
                        )}
                      >
                        {mission.completed && <Check size={11} />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-2">
                          <span
                            className={clsx(
                              'text-sm font-medium',
                              mission.completed ? 'text-ink-dim line-through' : 'text-ink',
                            )}
                          >
                            {mission.title}
                          </span>
                          <span className="tabular shrink-0 text-[11px] text-ink-dim">
                            {mission.progress}/{mission.target}
                          </span>
                        </div>
                        <p className="mt-0.5 text-xs text-ink-dim">{mission.description}</p>
                        <ProgressBar
                          className="mt-1.5"
                          value={(mission.progress / Math.max(1, mission.target)) * 100}
                          barClass={mission.completed ? 'bg-success' : 'bg-accent'}
                        />
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Weak areas" action={<Link to="/analytics/topics" className="text-xs text-ink-dim hover:text-ink">All</Link>}>
            {!data.has_enough_data && data.weaknesses.length === 0 ? (
              <Empty
                title="Not enough data yet"
                hint="Solve a few more problems across topics and weaknesses will surface here."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.weaknesses.map((weakness) => (
                  <li key={`${weakness.kind}-${weakness.slug}`} className="px-4 py-2.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-sm font-medium text-ink">{weakness.name}</span>
                      <span className={clsx('tabular text-xs', masteryColor(weakness.mastery))}>
                        {weakness.mastery.toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px]">
                      <span className={severityColor(weakness.severity)}>{weakness.severity}</span>
                      <span className="text-ink-dim">{weakness.root_cause_label}</span>
                    </div>
                    {weakness.evidence[0] && (
                      <p className="mt-1 text-xs text-ink-dim">{weakness.evidence[0].description}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Sheet progress">
            <ul className="space-y-3 px-4 py-3">
              {data.sheets.map((sheet) => (
                <li key={sheet.slug}>
                  <Link to={`/sheets/${sheet.slug}`} className="block group">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-sm text-ink group-hover:text-accent">{sheet.name}</span>
                      <span className="tabular text-xs text-ink-dim">
                        {sheet.completed}/{sheet.total} · {sheet.percent}%
                      </span>
                    </div>
                    <ProgressBar className="mt-1.5" value={sheet.percent} />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          {totals.reviews_due > 0 && (
            <Link to="/reviews" className="card card-hover block px-4 py-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-ink">
                    {totals.reviews_due} problem{totals.reviews_due === 1 ? '' : 's'} due for review
                  </div>
                  <div className="text-xs text-ink-dim">Retention compounds</div>
                </div>
                <ArrowUpRight size={16} className="text-ink-dim" />
              </div>
            </Link>
          )}
        </div>
      </div>

      <DayModal day={selectedDay} onClose={() => setSelectedDay(null)} />
    </div>
  );
}

function DayModal({ day, onClose }: { day: HeatmapDay | null; onClose: () => void }) {
  const { data, loading } = useApi(
    () => (day ? api.activityDay(day.date) : Promise.resolve(null)),
    [day?.date],
  );

  return (
    <Modal open={Boolean(day)} onClose={onClose} title={day ? formatDate(day.date) : ''}>
      {loading && <Loading />}
      {data && (
        <div className="px-4 py-4">
          <div className="mb-3 grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="tabular text-xl font-semibold">{data.problems.length}</div>
              <div className="label">Solved</div>
            </div>
            <div>
              <div className="tabular text-xl font-semibold text-accent">{data.xp}</div>
              <div className="label">XP</div>
            </div>
            <div>
              <div className="tabular text-xl font-semibold">{data.submissions}</div>
              <div className="label">Submissions</div>
            </div>
          </div>

          {data.frozen && (
            <p className="mb-3 rounded-lg bg-info/10 px-3 py-2 text-xs text-info">
              ❄ A streak freeze protected this day.
            </p>
          )}

          {data.problems.length === 0 ? (
            <Empty title="No problems solved on this day" />
          ) : (
            <ul className="divide-y divide-line">
              {data.problems.map((problem) => (
                <li key={problem.id} className="flex items-center justify-between gap-3 py-2">
                  <Link to={`/problems/${problem.id}`} onClick={onClose} className="truncate text-sm hover:text-accent">
                    {problem.title}
                  </Link>
                  <span className={clsx('shrink-0 font-mono text-xs', ratingColor(problem.rating))}>
                    {problem.rating ?? '—'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}
