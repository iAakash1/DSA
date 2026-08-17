/** Achievement grid, backed by real unlock state. */

import { useState } from 'react';
import { Lock, Trophy } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Loading, ProgressBar } from '../components/ui';
import { formatDate } from '../lib/format';

const TIER_STYLE: Record<string, string> = {
  bronze: 'text-[#c8853f] border-[#c8853f]/30',
  silver: 'text-[#b6c0d0] border-[#b6c0d0]/30',
  gold: 'text-accent border-accent/30',
  platinum: 'text-info border-info/30',
};

export function Achievements() {
  const { data, loading, error, reload } = useApi(() => api.achievements(), []);
  const [filter, setFilter] = useState<'all' | 'unlocked' | 'locked'>('all');

  if (loading) return <Loading label="Loading achievements" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const categories = Array.from(new Set(data.items.map((item) => item.category)));
  const visible = data.items.filter((item) =>
    filter === 'all' ? true : filter === 'unlocked' ? item.unlocked : !item.unlocked,
  );

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Achievements</h1>
          <p className="text-sm text-ink-dim">
            {data.unlocked_count} of {data.total} unlocked
          </p>
        </div>
        <div className="flex gap-1.5">
          {(['all', 'unlocked', 'locked'] as const).map((value) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={clsx('btn', filter === value ? 'btn-primary' : 'btn-ghost')}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      <ProgressBar value={(data.unlocked_count / Math.max(1, data.total)) * 100} height="h-2" />

      {visible.length === 0 ? (
        <Card>
          <Empty title="Nothing here" icon={<Trophy size={20} />} />
        </Card>
      ) : (
        categories.map((category) => {
          const items = visible.filter((item) => item.category === category);
          if (items.length === 0) return null;
          return (
            <div key={category}>
              <h2 className="label mb-2">{category}</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((item) => (
                  <div
                    key={item.code}
                    className={clsx(
                      'card px-4 py-3 transition-opacity',
                      item.unlocked ? 'border-l-2' : 'opacity-55',
                      item.unlocked && TIER_STYLE[item.tier],
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span
                        className={clsx(
                          'text-sm font-semibold',
                          item.unlocked ? 'text-ink' : 'text-ink-muted',
                        )}
                      >
                        {item.name}
                      </span>
                      {item.unlocked ? (
                        <Trophy size={14} className={TIER_STYLE[item.tier]?.split(' ')[0]} />
                      ) : (
                        <Lock size={13} className="text-ink-dim" />
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink-dim">{item.description}</p>
                    <div className="mt-2 flex items-center justify-between text-[11px]">
                      <span className="text-ink-dim">
                        {item.unlocked && item.unlocked_at
                          ? formatDate(item.unlocked_at)
                          : item.tier}
                      </span>
                      {item.xp_reward > 0 && (
                        <span className="text-accent">+{item.xp_reward} XP</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
