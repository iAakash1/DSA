/** Spaced-repetition review queue. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Clock, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Loading } from '../components/ui';
import { formatDate, problemRef, ratingColor } from '../lib/format';

const OUTCOMES = [
  { value: 'recalled', label: 'Recalled it', icon: CheckCircle2, className: 'text-success' },
  { value: 'partial', label: 'Partially', icon: Clock, className: 'text-accent' },
  { value: 'forgotten', label: 'Forgot it', icon: XCircle, className: 'text-danger' },
];

export function Reviews() {
  const [includeUpcoming, setIncludeUpcoming] = useState(false);
  const { data, loading, error, reload } = useApi(
    () => api.reviews(includeUpcoming),
    [includeUpcoming],
  );
  const [busy, setBusy] = useState<string | null>(null);

  async function complete(id: string, outcome: string) {
    setBusy(id);
    try {
      await api.completeReview(id, outcome);
      reload();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Review queue</h1>
          <p className="text-sm text-ink-dim">
            Problems enter this queue because of a signal — an editorial, a low confidence score, a
            repeated mistake — not because time passed.
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={includeUpcoming}
            onChange={(e) => setIncludeUpcoming(e.target.checked)}
          />
          Include upcoming
        </label>
      </div>

      <Card
        title={`${data?.due_count ?? 0} due now`}
        subtitle={includeUpcoming ? 'Showing scheduled reviews too' : undefined}
      >
        {loading && <Loading />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && data.items.length === 0 && (
          <Empty
            title="Nothing to review"
            hint="Reviews are scheduled automatically when a solve shows a weakness signal."
          />
        )}
        {data && data.items.length > 0 && (
          <ul className="divide-y divide-line">
            {data.items.map((review) => (
              <li key={review.id} className="px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link
                      to={`/problems/${review.problem_id}`}
                      className="font-medium text-ink hover:text-accent"
                    >
                      {review.problem.title}
                    </Link>
                    <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-ink-dim">
                      <span>
                        {problemRef(review.problem)}
                      </span>
                      {review.problem.rating && (
                        <span className={ratingColor(review.problem.rating)}>
                          {review.problem.rating}
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-xs text-ink-muted">{review.reason_detail}</p>
                    <p className="mt-0.5 text-[11px] text-ink-dim">
                      Scheduled {formatDate(review.scheduled_for)} · interval {review.interval_days}d
                    </p>
                  </div>

                  <div className="flex shrink-0 gap-1.5">
                    {OUTCOMES.map((outcome) => (
                      <button
                        key={outcome.value}
                        disabled={busy === review.id}
                        onClick={() => complete(review.id, outcome.value)}
                        className={clsx('btn btn-ghost disabled:opacity-40', outcome.className)}
                        title={outcome.label}
                      >
                        <outcome.icon size={14} />
                        <span className="hidden sm:inline">{outcome.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
