/** Formatting helpers shared across the UI. */

export function ratingColor(rating: number | null | undefined): string {
  if (!rating) return 'text-ink-dim';
  if (rating < 1200) return 'text-[#9aa3b5]';
  if (rating < 1400) return 'text-[#35c86f]';
  if (rating < 1600) return 'text-[#3bc9c9]';
  if (rating < 1900) return 'text-[#4d94f5]';
  if (rating < 2100) return 'text-[#9b7bf0]';
  if (rating < 2400) return 'text-[#f5a524]';
  return 'text-[#f0555a]';
}

export function difficultyColor(difficulty: string): string {
  switch (difficulty) {
    case 'easy':
      return 'text-success';
    case 'medium':
      return 'text-accent';
    case 'hard':
      return 'text-danger';
    default:
      return 'text-ink-dim';
  }
}

export function statusColor(status: string): string {
  switch (status) {
    case 'solved':
      return 'text-success';
    case 'mastered':
      return 'text-info';
    case 'attempted':
      return 'text-accent';
    case 'revisit':
      return 'text-violet';
    case 'skipped':
      return 'text-ink-dim';
    default:
      return 'text-ink-dim';
  }
}

export function masteryColor(value: number): string {
  if (value >= 81) return 'text-info';
  if (value >= 61) return 'text-success';
  if (value >= 41) return 'text-accent';
  if (value >= 21) return 'text-[#f08a24]';
  return 'text-danger';
}

export function severityColor(severity: string): string {
  switch (severity) {
    case 'high':
      return 'text-danger';
    case 'medium':
      return 'text-accent';
    default:
      return 'text-ink-muted';
  }
}

export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '—';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '—';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}

export function relativeDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function platformLabel(platform: string): string {
  switch (platform) {
    case 'codeforces':
      return 'CF';
    case 'leetcode':
      return 'LC';
    case 'takeuforward':
      return 'TUF';
    default:
      return platform.toUpperCase();
  }
}

/**
 * The short reference shown next to a problem: "CF 1400B", "LC two-sum".
 *
 * takeUforward problems are keyed by a numeric id because their slugs are
 * reused across different problems — useful as identity, meaningless on
 * screen — so they show the slug instead.
 */
export function problemRef(problem: {
  platform: string;
  external_id: string;
  slug?: string | null;
}): string {
  const identifier =
    problem.platform === 'takeuforward' ? problem.slug || problem.external_id : problem.external_id;
  return `${platformLabel(problem.platform)} ${identifier}`;
}

export function signed(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value > 0 ? `+${value}` : String(value);
}
