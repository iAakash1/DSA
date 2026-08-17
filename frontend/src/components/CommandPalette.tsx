/** Cmd/Ctrl+K command palette: search problems and jump anywhere. */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import clsx from 'clsx';
import { api, type SearchResults } from '../lib/api';
import { problemRef, ratingColor } from '../lib/format';

interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  onAddProblem,
  onSync,
}: {
  open: boolean;
  onClose: () => void;
  onAddProblem: () => void;
  onSync: () => void;
}) {
  const navigate = useNavigate();
  const [term, setTerm] = useState('');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setTerm('');
      setResults(null);
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  // Debounced search — the palette should feel instant, not chatty.
  useEffect(() => {
    if (!term.trim()) {
      setResults(null);
      return;
    }
    const handle = setTimeout(() => {
      api.search(term).then(setResults).catch(() => setResults(null));
    }, 160);
    return () => clearTimeout(handle);
  }, [term]);

  const staticCommands: Command[] = useMemo(() => {
    const go = (path: string) => () => {
      navigate(path);
      onClose();
    };
    return [
      { id: 'dashboard', label: 'Go to Dashboard', hint: 'D', run: go('/') },
      { id: 'problems', label: 'Go to Problems', hint: 'P', run: go('/problems') },
      { id: 'cp31', label: 'Open CP-31', run: go('/sheets/cp31') },
      { id: 'striver', label: 'Open Striver A2Z', run: go('/sheets/striver-a2z') },
      { id: 'reviews', label: 'Open Review Queue', run: go('/reviews') },
      { id: 'weak', label: 'View Weak Topics', run: go('/analytics/topics') },
      { id: 'coach', label: 'Ask the AI Coach', run: go('/coach') },
      { id: 'contests', label: 'Open Contests', run: go('/contests') },
      { id: 'achievements', label: 'Open Achievements', run: go('/achievements') },
      { id: 'settings', label: 'Open Settings', run: go('/settings') },
      {
        id: 'add',
        label: 'Add a problem',
        hint: 'A',
        run: () => {
          onAddProblem();
          onClose();
        },
      },
      {
        id: 'sync',
        label: 'Sync platform accounts',
        run: () => {
          onSync();
          onClose();
        },
      },
    ];
  }, [navigate, onClose, onAddProblem, onSync]);

  const filtered = useMemo(() => {
    if (!term.trim()) return staticCommands;
    const needle = term.toLowerCase();
    return staticCommands.filter((c) => c.label.toLowerCase().includes(needle));
  }, [staticCommands, term]);

  const problems = results?.problems ?? [];
  const total = filtered.length + problems.length;

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') return onClose();
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActive((i) => (i + 1) % Math.max(1, total));
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActive((i) => (i - 1 + Math.max(1, total)) % Math.max(1, total));
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        if (active < filtered.length) filtered[active]?.run();
        else {
          const problem = problems[active - filtered.length];
          if (problem) {
            navigate(`/problems/${problem.id}`);
            onClose();
          }
        }
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, active, total, filtered, problems, navigate, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/70 p-4 pt-[12vh] backdrop-blur-sm">
      <div className="absolute inset-0" onClick={onClose} aria-hidden />
      <div className="card animate-in relative w-full max-w-xl overflow-hidden">
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <Search size={15} className="text-ink-dim" />
          <input
            ref={inputRef}
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setActive(0);
            }}
            placeholder="Search problems or run a command…"
            className="w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-dim"
          />
          <kbd className="chip font-mono">ESC</kbd>
        </div>

        <div className="max-h-[55vh] overflow-y-auto py-1">
          {filtered.map((command, index) => (
            <button
              key={command.id}
              onMouseEnter={() => setActive(index)}
              onClick={command.run}
              className={clsx(
                'flex w-full items-center justify-between px-4 py-2 text-left text-sm',
                active === index ? 'bg-surface-3 text-ink' : 'text-ink-muted',
              )}
            >
              {command.label}
              {command.hint && <kbd className="chip font-mono">{command.hint}</kbd>}
            </button>
          ))}

          {problems.length > 0 && (
            <div className="mt-1 border-t border-line pt-1">
              <div className="label px-4 py-1">Problems</div>
              {problems.map((problem, i) => {
                const index = filtered.length + i;
                return (
                  <button
                    key={problem.id}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => {
                      navigate(`/problems/${problem.id}`);
                      onClose();
                    }}
                    className={clsx(
                      'flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm',
                      active === index ? 'bg-surface-3 text-ink' : 'text-ink-muted',
                    )}
                  >
                    <span className="truncate">{problem.title}</span>
                    <span className="flex shrink-0 items-center gap-2 font-mono text-[11px]">
                      <span className="text-ink-dim">
                        {problemRef(problem)}
                      </span>
                      <span className={ratingColor(problem.rating)}>{problem.rating ?? ''}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {total === 0 && (
            <div className="px-4 py-8 text-center text-sm text-ink-dim">No matches</div>
          )}
        </div>
      </div>
    </div>
  );
}
