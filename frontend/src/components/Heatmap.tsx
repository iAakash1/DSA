/** GitHub-style 365-day activity grid. */

import { useMemo, useState } from 'react';
import clsx from 'clsx';
import type { HeatmapDay } from '../lib/api';

const HEAT = [
  'bg-[var(--color-heat-0)]',
  'bg-[var(--color-heat-1)]',
  'bg-[var(--color-heat-2)]',
  'bg-[var(--color-heat-3)]',
  'bg-[var(--color-heat-4)]',
];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function Heatmap({
  days,
  onSelect,
}: {
  days: HeatmapDay[];
  onSelect?: (day: HeatmapDay) => void;
}) {
  const [hovered, setHovered] = useState<HeatmapDay | null>(null);

  // Group into calendar weeks, padding the first week so rows are weekdays.
  const weeks = useMemo(() => {
    if (!days.length) return [];
    const result: (HeatmapDay | null)[][] = [];
    let current: (HeatmapDay | null)[] = [];

    const firstDow = new Date(days[0].date).getDay();
    for (let i = 0; i < firstDow; i += 1) current.push(null);

    for (const day of days) {
      current.push(day);
      if (current.length === 7) {
        result.push(current);
        current = [];
      }
    }
    if (current.length) {
      while (current.length < 7) current.push(null);
      result.push(current);
    }
    return result;
  }, [days]);

  const monthLabels = useMemo(() => {
    const labels: { index: number; label: string }[] = [];
    let lastMonth = -1;
    weeks.forEach((week, index) => {
      const first = week.find(Boolean);
      if (!first) return;
      const month = new Date(first.date).getMonth();
      if (month !== lastMonth) {
        labels.push({ index, label: MONTHS[month] });
        lastMonth = month;
      }
    });
    return labels;
  }, [weeks]);

  return (
    <div className="relative">
      <div className="overflow-x-auto pb-1">
        <div className="inline-block min-w-full">
          <div className="relative mb-1 h-4">
            {monthLabels.map(({ index, label }) => (
              <span
                key={`${label}-${index}`}
                className="absolute text-[10px] text-ink-dim"
                style={{ left: `${index * 13}px` }}
              >
                {label}
              </span>
            ))}
          </div>

          <div className="flex gap-[3px]">
            {weeks.map((week, wi) => (
              <div key={wi} className="flex flex-col gap-[3px]">
                {week.map((day, di) =>
                  day ? (
                    <button
                      key={day.date}
                      type="button"
                      onMouseEnter={() => setHovered(day)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() => onSelect?.(day)}
                      aria-label={`${day.date}: ${day.count} solved`}
                      className={clsx(
                        'h-[10px] w-[10px] rounded-[2px] transition-transform hover:scale-125',
                        HEAT[day.intensity] ?? HEAT[0],
                        day.frozen && 'ring-1 ring-info',
                      )}
                    />
                  ) : (
                    <div key={`${wi}-${di}`} className="h-[10px] w-[10px]" />
                  ),
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px] text-ink-dim">
        <span>
          {hovered ? (
            <span className="text-ink-muted">
              <span className="font-medium text-ink">{hovered.count}</span> solved ·{' '}
              {hovered.xp} XP{hovered.minutes ? ` · ${hovered.minutes}m` : ''}
              {hovered.frozen ? ' · ❄ frozen' : ''} — {hovered.date}
            </span>
          ) : (
            'Hover a day for detail, click to open it'
          )}
        </span>
        <span className="flex items-center gap-1">
          Less
          {HEAT.map((cls, i) => (
            <span key={i} className={clsx('h-[10px] w-[10px] rounded-[2px]', cls)} />
          ))}
          More
        </span>
      </div>
    </div>
  );
}
