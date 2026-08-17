/** Profile, goals, connected accounts, AI settings and data export. */

import { useEffect, useState } from 'react';
import { Check, Download, RefreshCw, Snowflake } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useAction, useApi } from '../hooks/useApi';
import { Card, ErrorState, Field, Loading, inputClass } from '../components/ui';
import { authMode } from '../lib/auth';
import { formatDate } from '../lib/format';

export function Settings() {
  const me = useApi(() => api.me(), []);
  const health = useApi(() => api.health(), []);
  const freezes = useApi(() => api.freezes(), []);
  const usage = useApi(() => api.aiUsage(), []);

  if (me.loading) return <Loading label="Loading settings" />;
  if (me.error) return <ErrorState error={me.error} onRetry={me.reload} />;
  if (!me.data) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-lg font-semibold">Settings</h1>

      <ProfileCard me={me.data} onSaved={me.reload} />
      <GoalsCard me={me.data} onSaved={me.reload} />
      <AccountsCard accounts={me.data.accounts} onChanged={me.reload} />

      <Card title="Streak freezes" subtitle="Protect a missed day; every movement is recorded">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Snowflake size={16} className="text-info" />
              <span className="tabular text-lg font-semibold">{freezes.data?.available ?? 0}</span>
              <span className="text-sm text-ink-dim">
                available · costs {String(me.data.settings.freeze_cost_xp ?? 500)} XP
              </span>
            </div>
            <BuyFreezeButton onDone={freezes.reload} />
          </div>
          {(freezes.data?.transactions.length ?? 0) > 0 && (
            <ul className="mt-3 space-y-1 border-t border-line pt-2.5">
              {freezes.data!.transactions.slice(0, 5).map((tx) => (
                <li key={tx.id} className="flex justify-between text-xs text-ink-dim">
                  <span>
                    {tx.kind} {tx.note ? `· ${tx.note}` : ''}
                  </span>
                  <span>{formatDate(tx.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <Card title="AI Coach" subtitle="Inference runs server-side; no key ever reaches the browser">
        <div className="space-y-2 px-4 py-3 text-sm">
          <Row label="Status">
            {health.data?.features.ai_configured ? (
              <span className="text-success">configured</span>
            ) : (
              <span className="text-accent">no API key configured</span>
            )}
          </Row>
          {usage.data?.available && (
            <>
              <Row label="Model">
                <span className="font-mono text-xs">{usage.data.model}</span>
              </Row>
              <Row label="Requests today">
                {usage.data.today.requests} / {usage.data.daily_budget}
              </Row>
              <Row label="Tokens (30d)">
                {(usage.data.last_30_days.input_tokens + usage.data.last_30_days.output_tokens).toLocaleString()}
              </Row>
              <Row label="Avg latency">{usage.data.today.average_latency_ms} ms</Row>
            </>
          )}
        </div>
      </Card>

      <Card title="System">
        <div className="space-y-2 px-4 py-3 text-sm">
          <Row label="Auth mode">
            <span className="font-mono text-xs">
              {authMode === 'local' ? 'local (single user)' : authMode}
            </span>
          </Row>
          <Row label="Database">
            <span className="font-mono text-xs">
              {health.data?.status === 'ok' ? 'connected' : 'unavailable'}
            </span>
          </Row>
          <Row label="Video search">
            {health.data?.features.youtube_configured ? (
              <span className="text-success">configured</span>
            ) : (
              <span className="text-ink-dim">not configured</span>
            )}
          </Row>
        </div>
      </Card>

      <Card title="Your data" subtitle="Everything is exportable — you are never locked in">
        <div className="px-4 py-3">
          <button
            onClick={async () => {
              const data = await api.exportData();
              const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement('a');
              anchor.href = url;
              anchor.download = `cp-forge-export-${new Date().toISOString().slice(0, 10)}.json`;
              anchor.click();
              URL.revokeObjectURL(url);
            }}
            className="btn btn-ghost"
          >
            <Download size={14} /> Export everything as JSON
          </button>
        </div>
      </Card>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-dim">{label}</span>
      <span className="text-ink-muted">{children}</span>
    </div>
  );
}

function ProfileCard({ me, onSaved }: { me: { username: string; display_name: string | null; timezone: string }; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState(me.display_name ?? '');
  const [timezone, setTimezone] = useState(me.timezone);
  const [save, { pending, error }] = useAction(api.updateMe);
  const [saved, setSaved] = useState(false);

  const zones =
    typeof Intl.supportedValuesOf === 'function'
      ? (Intl.supportedValuesOf('timeZone') as string[])
      : [me.timezone, 'UTC'];

  return (
    <Card title="Profile" subtitle="Your timezone decides when a day starts for streaks">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const ok = await save({ display_name: displayName, timezone });
          if (ok !== null) {
            setSaved(true);
            onSaved();
            setTimeout(() => setSaved(false), 2000);
          }
        }}
        className="space-y-3 px-4 py-3"
      >
        <Field label="Display name">
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Timezone">
          <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className={inputClass}>
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </Field>
        {error && <p className="text-xs text-danger">{error.message}</p>}
        <button type="submit" disabled={pending} className="btn btn-primary disabled:opacity-50">
          {saved ? <><Check size={13} /> Saved</> : pending ? 'Saving…' : 'Save profile'}
        </button>
      </form>
    </Card>
  );
}

function GoalsCard({ me, onSaved }: { me: { settings: Record<string, unknown> }; onSaved: () => void }) {
  const [daily, setDaily] = useState(Number(me.settings.daily_goal ?? 2));
  const [weekly, setWeekly] = useState(Number(me.settings.weekly_goal ?? 14));
  const [autoFreeze, setAutoFreeze] = useState(Boolean(me.settings.auto_apply_freeze));
  const [save, { pending }] = useAction(api.updateSettings);
  const [saved, setSaved] = useState(false);

  return (
    <Card title="Goals">
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const ok = await save({ daily_goal: daily, weekly_goal: weekly, auto_apply_freeze: autoFreeze });
          if (ok !== null) {
            setSaved(true);
            onSaved();
            setTimeout(() => setSaved(false), 2000);
          }
        }}
        className="space-y-3 px-4 py-3"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Daily problem goal">
            <input
              type="number"
              min={1}
              max={50}
              value={daily}
              onChange={(e) => setDaily(Number(e.target.value))}
              className={inputClass}
            />
          </Field>
          <Field label="Weekly problem goal">
            <input
              type="number"
              min={1}
              max={300}
              value={weekly}
              onChange={(e) => setWeekly(Number(e.target.value))}
              className={inputClass}
            />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          <input type="checkbox" checked={autoFreeze} onChange={(e) => setAutoFreeze(e.target.checked)} />
          Automatically spend a freeze to protect a missed day
        </label>
        <button type="submit" disabled={pending} className="btn btn-primary disabled:opacity-50">
          {saved ? <><Check size={13} /> Saved</> : 'Save goals'}
        </button>
      </form>
    </Card>
  );
}

function AccountsCard({
  accounts,
  onChanged,
}: {
  accounts: { platform: string; username: string; last_synced_at: string | null; last_sync_status: string | null; last_sync_error: string | null; current_rating: number | null }[];
  onChanged: () => void;
}) {
  const [cf, setCf] = useState('');
  const [lc, setLc] = useState('');
  const [syncing, setSyncing] = useState<string | null>(null);
  const [connect, { pending }] = useAction(api.connectAccount);

  useEffect(() => {
    setCf(accounts.find((a) => a.platform === 'codeforces')?.username ?? '');
    setLc(accounts.find((a) => a.platform === 'leetcode')?.username ?? '');
  }, [accounts]);

  async function sync(platform: string) {
    setSyncing(platform);
    try {
      await api.sync(platform);
      onChanged();
    } finally {
      setSyncing(null);
    }
  }

  const rows: { platform: string; label: string; value: string; setValue: (v: string) => void }[] = [
    { platform: 'codeforces', label: 'Codeforces handle', value: cf, setValue: setCf },
    { platform: 'leetcode', label: 'LeetCode username', value: lc, setValue: setLc },
  ];

  return (
    <Card title="Connected accounts" subtitle="A profile URL works too — it is normalised for you">
      <div className="space-y-4 px-4 py-3">
        {rows.map((row) => {
          const account = accounts.find((a) => a.platform === row.platform);
          return (
            <div key={row.platform}>
              <Field label={row.label}>
                <div className="flex gap-2">
                  <input
                    value={row.value}
                    onChange={(e) => row.setValue(e.target.value)}
                    placeholder={row.platform === 'codeforces' ? 'tourist' : 'username'}
                    className={inputClass}
                  />
                  <button
                    onClick={async () => {
                      if (!row.value.trim()) return;
                      await connect({ platform: row.platform, username: row.value });
                      onChanged();
                    }}
                    disabled={pending}
                    className="btn btn-ghost shrink-0"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => sync(row.platform)}
                    disabled={!account || syncing === row.platform}
                    className="btn btn-ghost shrink-0 disabled:opacity-40"
                  >
                    <RefreshCw size={13} className={clsx(syncing === row.platform && 'animate-spin')} />
                    Sync
                  </button>
                </div>
              </Field>
              {account && (
                <p className="mt-1 text-xs text-ink-dim">
                  {account.last_sync_status === 'failed' ? (
                    <span className="text-danger">Last sync failed: {account.last_sync_error}</span>
                  ) : account.last_synced_at ? (
                    <>
                      Last synced {formatDate(account.last_synced_at)}
                      {account.current_rating ? ` · rating ${account.current_rating}` : ''}
                    </>
                  ) : (
                    'Never synced'
                  )}
                </p>
              )}
              {row.platform === 'leetcode' && (
                <p className="mt-1 text-xs text-ink-dim">
                  LeetCode's public API exposes only the ~20 most recent accepted submissions, so
                  sync regularly to build full history.
                </p>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function BuyFreezeButton({ onDone }: { onDone: () => void }) {
  const [buy, { pending }] = useAction(api.buyFreeze);
  const [message, setMessage] = useState<string | null>(null);

  return (
    <div className="text-right">
      <button
        onClick={async () => {
          const result = await buy();
          if (result) {
            setMessage(result.purchased ? 'Purchased' : (result.reason ?? null));
            onDone();
            setTimeout(() => setMessage(null), 3000);
          }
        }}
        disabled={pending}
        className="btn btn-ghost disabled:opacity-50"
      >
        Buy a freeze
      </button>
      {message && <p className="mt-1 text-xs text-ink-dim">{message}</p>}
    </div>
  );
}
