/**
 * The AI Coach panel.
 *
 * Always shows *something*: when AI is unavailable it renders the deterministic
 * fallback the backend returned, clearly labelled, instead of an error.
 * "Why am I seeing this?" expands the exact metrics behind the insight.
 */

import { useState } from 'react';
import { ChevronDown, RefreshCw, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import type { Insight } from '../lib/api';
import { Loading } from './ui';

export function AICoachCard({
  insight,
  loading,
  onRefresh,
  refreshing,
}: {
  insight: Insight | null;
  loading: boolean;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const [showWhy, setShowWhy] = useState(false);

  if (loading) {
    return (
      <section className="card">
        <Loading label="Analysing your data" />
      </section>
    );
  }

  if (!insight) return null;

  const structured = insight.structured_output ?? {};
  const evidence = structured.evidence ?? [];
  const actions = structured.recommendations ?? [];

  return (
    <section className="card animate-in overflow-hidden">
      <header className="flex items-center justify-between border-b border-line bg-gradient-to-r from-accent-soft/60 to-transparent px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-accent" />
          <h2 className="text-sm font-semibold tracking-wide">AI COACH</h2>
          {!insight.ai_generated && (
            <span className="chip bg-surface-3 text-ink-dim">deterministic</span>
          )}
          {insight.cached && insight.ai_generated && (
            <span className="chip bg-surface-3 text-ink-dim">cached</span>
          )}
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="rounded p-1 text-ink-dim hover:bg-surface-3 hover:text-ink disabled:opacity-50"
            title="Regenerate"
          >
            <RefreshCw size={13} className={clsx(refreshing && 'animate-spin')} />
          </button>
        )}
      </header>

      <div className="px-4 py-3">
        <h3 className="text-base font-semibold text-ink">{insight.title}</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{insight.summary}</p>

        {structured.diagnosis && (
          <p className="mt-2.5 border-l-2 border-line-strong pl-3 text-sm leading-relaxed text-ink-muted">
            {structured.diagnosis}
          </p>
        )}

        {insight.message && (
          <p className="mt-2.5 rounded-lg bg-surface-2 px-3 py-2 text-xs text-ink-dim">
            {insight.message}
          </p>
        )}

        {actions.length > 0 && (
          <div className="mt-3">
            <span className="label">Recommended focus</span>
            <ul className="mt-1.5 space-y-1.5">
              {actions.map((item, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="mt-[3px] text-accent">→</span>
                  <div>
                    <span className="text-ink">{item.action}</span>
                    {item.reason && (
                      <span className="block text-xs text-ink-dim">{item.reason}</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {evidence.length > 0 && (
          <div className="mt-3 border-t border-line pt-2.5">
            <button
              onClick={() => setShowWhy((v) => !v)}
              className="flex items-center gap-1 text-xs text-ink-dim hover:text-ink-muted"
              aria-expanded={showWhy}
            >
              <ChevronDown
                size={13}
                className={clsx('transition-transform', showWhy && 'rotate-180')}
              />
              Why am I seeing this?
            </button>

            {showWhy && (
              <dl className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {evidence.map((item, i) => (
                  <div key={i} className="rounded-lg bg-surface-2 px-3 py-2">
                    <dt className="font-mono text-[11px] text-ink-dim">{item.metric}</dt>
                    <dd className="tabular text-sm font-medium text-ink">
                      {item.value}
                      {item.comparison && (
                        <span className="ml-1.5 text-xs font-normal text-ink-dim">
                          vs {item.comparison}
                        </span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        )}

        <div className="mt-3 flex items-center gap-3 text-[11px] text-ink-dim">
          <span>confidence: {insight.confidence.replace('_', ' ')}</span>
          {insight.model && <span className="font-mono">{insight.model}</span>}
        </div>
      </div>
    </section>
  );
}
