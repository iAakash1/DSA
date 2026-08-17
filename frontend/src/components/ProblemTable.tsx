/** Dense problem list used by the explorer, sheets and collections. */

import { Check, CircleDashed, ExternalLink, RotateCcw, Star } from 'lucide-react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import { difficultyColor, problemRef, ratingColor, relativeDate } from '../lib/format';

export interface TableRow {
  problem_id?: string;
  id?: string;
  title: string;
  platform: string;
  external_id: string;
  url: string;
  rating: number | null;
  difficulty: string;
  status: string;
  solved_at?: string | null;
  needs_review?: boolean;
  is_favorite?: boolean;
  section_name?: string | null;
  tags?: string[];
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'solved' || status === 'mastered')
    return <Check size={14} className="text-success" aria-label="Solved" />;
  if (status === 'revisit') return <RotateCcw size={13} className="text-violet" aria-label="Revisit" />;
  if (status === 'attempted')
    return <CircleDashed size={13} className="text-accent" aria-label="Attempted" />;
  return <CircleDashed size={13} className="text-ink-dim/50" aria-label="Unsolved" />;
}

export function ProblemTable({
  rows,
  showSection,
  onMarkSolved,
}: {
  rows: TableRow[];
  showSection?: boolean;
  onMarkSolved?: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <th className="w-8 px-3 py-2" />
            <th className="px-2 py-2 label">Problem</th>
            {showSection && <th className="px-2 py-2 label">Section</th>}
            <th className="w-16 px-2 py-2 label">Rating</th>
            <th className="w-20 px-2 py-2 label">Solved</th>
            <th className="w-16 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const id = row.problem_id ?? row.id ?? row.external_id;
            return (
              <tr key={id} className="group border-b border-line/60 hover:bg-surface-2">
                <td className="px-3 py-2 align-middle">
                  <StatusIcon status={row.status} />
                </td>
                <td className="px-2 py-2">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/problems/${id}`}
                      className="truncate font-medium text-ink hover:text-accent"
                    >
                      {row.title}
                    </Link>
                    {row.is_favorite && <Star size={11} className="shrink-0 text-accent" />}
                    {row.needs_review && (
                      <span className="chip shrink-0 bg-violet/15 text-violet">review</span>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-dim">
                    <span className="font-mono">
                      {problemRef(row)}
                    </span>
                    {row.difficulty !== 'unknown' && (
                      <span className={difficultyColor(row.difficulty)}>{row.difficulty}</span>
                    )}
                  </div>
                </td>
                {showSection && (
                  <td className="px-2 py-2 text-xs text-ink-muted">{row.section_name ?? '—'}</td>
                )}
                <td className={clsx('tabular px-2 py-2 font-mono text-xs', ratingColor(row.rating))}>
                  {row.rating ?? '—'}
                </td>
                <td className="px-2 py-2 text-xs text-ink-dim">{relativeDate(row.solved_at)}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    {onMarkSolved && row.status !== 'solved' && row.status !== 'mastered' && (
                      <button
                        onClick={() => onMarkSolved(id)}
                        className="rounded p-1 text-ink-dim hover:bg-surface-3 hover:text-success"
                        title="Mark solved"
                      >
                        <Check size={14} />
                      </button>
                    )}
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="rounded p-1 text-ink-dim hover:bg-surface-3 hover:text-ink"
                      title="Open on platform"
                    >
                      <ExternalLink size={13} />
                    </a>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
