/** Analytics overview. Every chart is backed by a real API response. */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Loading, StatTile } from '../components/ui';
import { formatMinutes, percent, signed } from '../lib/format';

const AXIS = { stroke: '#646d80', fontSize: 11 };
const GRID = '#232936';

const tooltipStyle = {
  backgroundColor: '#12151c',
  border: '1px solid #2e3543',
  borderRadius: 8,
  fontSize: 12,
  color: '#e8eaf0',
};

export function Analytics() {
  const stats = useApi(() => api.stats(), []);
  const difficulty = useApi(() => api.difficulty(), []);
  const weekly = useApi(() => api.recentActivity(), []);
  const time = useApi(() => api.solveTime(), []);

  if (stats.loading) return <Loading label="Computing analytics" />;
  if (stats.error) return <ErrorState error={stats.error} onRetry={stats.reload} />;
  if (!stats.data) return null;

  const s = stats.data;
  const volume = s.volume as Record<string, number | null>;
  const diff = s.difficulty as Record<string, number | null>;

  const independenceData = Object.entries(s.independence.counts)
    .filter(([, count]) => count > 0)
    .map(([source, count]) => ({ source: source.replace('_', ' '), count }));

  const hasData = (volume.solved_total ?? 0) > 0;

  if (!hasData) {
    return (
      <div className="mx-auto max-w-3xl">
        <Card>
          <Empty
            title="No analytics yet"
            hint="Sync a platform account or record a solve, and this page fills with real numbers."
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <h1 className="text-lg font-semibold">Analytics</h1>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile
          label="Solved (30d)"
          value={volume.solved_last_30_days ?? 0}
          hint={
            volume.volume_change_30d !== null && volume.volume_change_30d !== undefined
              ? `${signed(volume.volume_change_30d)}% vs prev`
              : `${volume.solved_total ?? 0} lifetime`
          }
        />
        <StatTile
          label="Avg rating"
          value={diff.average_cf_rating ?? '—'}
          hint={
            diff.rating_change_30d
              ? `${signed(diff.rating_change_30d)} vs prev 30d`
              : `max ${diff.highest_cf_rating ?? '—'}`
          }
        />
        <StatTile label="Comfortable at" value={diff.comfortable_rating ?? '—'} hint="sustained 60%+ success" />
        <StatTile label="Success rate" value={percent(s.success_rate)} hint={`${s.submissions.total} submissions`} />
        <StatTile
          label="Independent"
          value={percent(s.independence.independent_rate)}
          hint={`of ${s.independence.reported_solves} self-reported`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Difficulty progression" subtitle="Average and peak solved rating per month">
          {difficulty.loading && <Loading />}
          {difficulty.data && difficulty.data.monthly.length > 0 ? (
            <div className="h-64 px-2 py-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={difficulty.data.monthly}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" {...AXIS} tickLine={false} />
                  <YAxis {...AXIS} tickLine={false} domain={['dataMin - 100', 'dataMax + 100']} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line
                    type="monotone"
                    dataKey="average_rating"
                    name="Average"
                    stroke="#f5a524"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="max_rating"
                    name="Peak"
                    stroke="#4d94f5"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="Not enough rated solves yet" />
          )}
        </Card>

        <Card title="Rating distribution" subtitle="How many problems solved at each band">
          {difficulty.data && difficulty.data.rating_distribution.length > 0 ? (
            <div className="h-64 px-2 py-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={difficulty.data.rating_distribution}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="rating" {...AXIS} tickLine={false} />
                  <YAxis {...AXIS} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#181c25' }} />
                  <Bar dataKey="solved" radius={[3, 3, 0, 0]}>
                    {difficulty.data.rating_distribution.map((entry) => (
                      <Cell
                        key={entry.rating}
                        fill={
                          difficulty.data && entry.rating >= (difficulty.data.comfortable_rating ?? 0)
                            ? '#f5a524'
                            : '#2e3543'
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="No rated problems solved yet" />
          )}
        </Card>

        <Card title="Solve time by topic" subtitle="Where your time actually goes">
          {time.data && time.data.by_topic.length > 0 ? (
            <div className="h-64 px-2 py-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={time.data.by_topic.slice(0, 8)} layout="vertical">
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" {...AXIS} tickLine={false} />
                  <YAxis dataKey="topic" type="category" width={110} {...AXIS} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#181c25' }} />
                  <Bar dataKey="average_minutes" name="Avg minutes" fill="#9b7bf0" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty
              title="No timed sessions yet"
              hint="Record time spent when you log a solve to unlock this."
            />
          )}
        </Card>

        <Card
          title="How you solve"
          subtitle="Self-reported sources; 'unknown' are platform syncs you have not labelled"
        >
          {independenceData.length > 0 ? (
            <div className="h-64 px-2 py-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={independenceData}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="source" {...AXIS} tickLine={false} />
                  <YAxis {...AXIS} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#181c25' }} />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {independenceData.map((entry) => (
                      // Unlabelled syncs are muted so they read as missing
                      // information rather than as an achievement.
                      <Cell
                        key={entry.source}
                        fill={entry.source === 'unknown' ? '#2e3543' : '#35c86f'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="No self-reported solves yet" />
          )}
          {s.independence.unreported_solves > 0 && (
            <p className="border-t border-line px-4 py-2 text-xs text-ink-dim">
              {s.independence.unreported_solves} synced solves carry no self-report and are excluded
              from these rates.
            </p>
          )}
        </Card>

        <Card title="Mistake distribution" subtitle="Implementation vs approach">
          {s.mistakes.total > 0 ? (
            <>
              <div className="h-56 px-2 py-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={s.mistakes.items.slice(0, 7)} layout="vertical">
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" {...AXIS} tickLine={false} allowDecimals={false} />
                    <YAxis dataKey="label" type="category" width={140} {...AXIS} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#181c25' }} />
                    <Bar dataKey="count" fill="#f0555a" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="border-t border-line px-4 py-2 text-xs text-ink-dim">
                {percent(s.mistakes.implementation_share)} of classified mistakes are implementation
                errors — {s.mistakes.implementation_share > 0.5
                  ? 'your approach selection is stronger than your execution.'
                  : 'these are mostly approach-level, not bugs.'}
              </p>
            </>
          ) : (
            <Empty
              title="No mistakes recorded"
              hint="Tag mistakes when you log a solve — this becomes one of the most useful charts here."
            />
          )}
        </Card>

        <Card title="Recent solves" subtitle="Latest activity">
          {weekly.data && weekly.data.length > 0 ? (
            <div className="h-56 px-2 py-3">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={weekly.data
                    .slice()
                    .reverse()
                    .map((item, i) => ({ i, rating: item.rating ?? 0, title: item.title }))}
                >
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="i" {...AXIS} tickLine={false} hide />
                  <YAxis {...AXIS} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={() => ''} />
                  <Area type="monotone" dataKey="rating" stroke="#f5a524" fill="#2a1f0d" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="No recent activity" />
          )}
        </Card>
      </div>

      <Card title="Time summary">
        <div className="grid grid-cols-2 gap-4 px-4 py-4 sm:grid-cols-4">
          {[
            ['Average solve', formatMinutes(s.time.average_solve_minutes)],
            ['Median solve', formatMinutes(s.time.median_solve_minutes)],
            ['Fastest', formatMinutes(s.time.fastest_solve_minutes)],
            ['Slowest', formatMinutes(s.time.slowest_solve_minutes)],
          ].map(([label, value]) => (
            <div key={label}>
              <div className="label">{label}</div>
              <div className="tabular mt-0.5 text-lg font-semibold">{value}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
