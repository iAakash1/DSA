/** Problem page: everything known about one problem, plus every write action. */

import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  BookOpen,
  Check,
  ExternalLink,
  FileText,
  Repeat,
  TriangleAlert,
  Youtube,
} from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useAction, useApi } from '../hooks/useApi';
import {
  Card,
  Empty,
  ErrorState,
  Field,
  Loading,
  Modal,
  inputClass,
} from '../components/ui';
import {
  difficultyColor,
  formatDate,
  formatDuration,
  problemRef,
  ratingColor,
  relativeDate,
  statusColor,
} from '../lib/format';

export function ProblemDetail() {
  const { id = '' } = useParams();
  const { data, loading, error, reload } = useApi(() => api.problem(id), [id]);
  const reference = useApi(() => api.reference(), []);
  const [solveOpen, setSolveOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [videoOpen, setVideoOpen] = useState(false);

  if (loading) return <Loading label="Loading problem" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const solved = data.status === 'solved' || data.status === 'mastered';

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-dim">
            <span className="font-mono">
              {problemRef(data)}
            </span>
            {data.rating && (
              <span className={clsx('font-mono', ratingColor(data.rating))}>{data.rating}</span>
            )}
            {data.difficulty !== 'unknown' && (
              <span className={difficultyColor(data.difficulty)}>{data.difficulty}</span>
            )}
            <span className={statusColor(data.status)}>{data.status}</span>
          </div>
          <h1 className="mt-1 text-xl font-semibold">{data.title}</h1>
        </div>

        <div className="flex flex-wrap gap-2">
          <a href={data.url} target="_blank" rel="noreferrer noopener" className="btn btn-ghost">
            Open <ExternalLink size={13} />
          </a>
          <button onClick={() => setVideoOpen(true)} className="btn btn-ghost">
            <Youtube size={14} /> Solution
          </button>
          <button onClick={() => setNoteOpen(true)} className="btn btn-ghost">
            <FileText size={14} /> Note
          </button>
          <button onClick={() => setSolveOpen(true)} className="btn btn-primary">
            <Check size={14} /> {solved ? 'Log another solve' : 'Mark solved'}
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Classification">
            <div className="space-y-3 px-4 py-3">
              <TagRow label="Topics" items={data.topics.map((t) => ({ key: t.slug, label: t.name, to: `/problems?topic=${t.slug}` }))} />
              <TagRow label="Patterns" items={data.patterns.map((p) => ({ key: p.slug, label: p.name, to: `/problems?pattern=${p.slug}` }))} />
              <TagRow
                label="Sheets"
                items={data.sheets.map((s) => ({
                  key: s.slug + (s.section ?? ''),
                  label: s.section ? `${s.name} · ${s.section}` : s.name,
                  to: `/sheets/${s.slug}`,
                }))}
              />
              <TagRow label="Collections" items={data.collections.map((c) => ({ key: c.slug, label: c.name, to: `/collections/${c.slug}` }))} />
              {data.tags.length > 0 && (
                <TagRow label="Platform tags" items={data.tags.map((t) => ({ key: t, label: t }))} />
              )}
            </div>
          </Card>

          <Card title="Solving history" subtitle={`${data.attempts} attempt${data.attempts === 1 ? '' : 's'}`}>
            {data.sessions.length === 0 ? (
              <Empty
                title="No recorded sessions"
                hint="Log a solve with time and confidence to unlock solve-time and independence analytics."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.sessions.map((session) => (
                  <li key={session.id} className="px-4 py-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className={clsx('text-sm font-medium', session.result === 'solved' ? 'text-success' : 'text-danger')}>
                        {session.result}
                      </span>
                      <span className="text-xs text-ink-dim">{relativeDate(session.finished_at)}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-ink-dim">
                      <span>{formatDuration(session.time_spent_seconds)}</span>
                      <span>{session.solution_source.replace('_', ' ')}</span>
                      {session.confidence && <span>confidence {session.confidence}/5</span>}
                      <span>{session.attempt_count}× attempts</span>
                    </div>
                    {session.approach && <p className="mt-1.5 text-sm text-ink-muted">{session.approach}</p>}
                    {session.notes && <p className="mt-1 text-xs text-ink-dim">{session.notes}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Notes" action={<button onClick={() => setNoteOpen(true)} className="text-xs text-ink-dim hover:text-ink">Add</button>}>
            {data.notes.length === 0 ? (
              <Empty title="No notes yet" hint="Capture the key insight while it is fresh." />
            ) : (
              <ul className="divide-y divide-line">
                {data.notes.map((note) => (
                  <li key={note.id} className="px-4 py-3">
                    <div className="flex items-center justify-between">
                      <span className="chip">{note.kind}</span>
                      <span className="text-[11px] text-ink-dim">{formatDate(note.created_at)}</span>
                    </div>
                    <p className="mt-1.5 whitespace-pre-wrap text-sm text-ink-muted">{note.content_md}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          {data.review && (
            <Card title="Review scheduled">
              <div className="px-4 py-3">
                <div className="flex items-center gap-2 text-sm text-violet">
                  <Repeat size={14} /> {formatDate(data.review.scheduled_for)}
                </div>
                <p className="mt-1 text-xs text-ink-dim">{data.review.reason_detail}</p>
              </div>
            </Card>
          )}

          {data.mistakes.length > 0 && (
            <Card title="Recorded mistakes">
              <ul className="divide-y divide-line">
                {data.mistakes.map((mistake) => (
                  <li key={mistake.id} className="flex items-center justify-between px-4 py-2">
                    <span className="flex items-center gap-1.5 text-sm text-danger">
                      <TriangleAlert size={12} />
                      {reference.data?.mistake_types.find((m) => m.value === mistake.type)?.label ?? mistake.type}
                    </span>
                    <span className="text-[11px] text-ink-dim">{relativeDate(mistake.occurred_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title="Related problems" subtitle="Shared topics, closest difficulty">
            {data.related.length === 0 ? (
              <Empty title="Nothing related yet" />
            ) : (
              <ul className="divide-y divide-line">
                {data.related.map((item) => (
                  <li key={item.id} className="px-4 py-2">
                    <Link to={`/problems/${item.id}`} className="block hover:text-accent">
                      <div className="truncate text-sm">{item.title}</div>
                      <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-ink-dim">
                        <span>{problemRef(item)}</span>
                        {item.rating && <span className={ratingColor(item.rating)}>{item.rating}</span>}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Actions">
            <div className="space-y-2 px-4 py-3">
              <StatusButtons problemId={id} current={data.status} onDone={reload} />
            </div>
          </Card>
        </div>
      </div>

      <SolveModal
        open={solveOpen}
        onClose={() => setSolveOpen(false)}
        problemId={id}
        mistakeTypes={reference.data?.mistake_types ?? []}
        sources={reference.data?.solution_sources ?? []}
        onDone={reload}
      />
      <NoteModal open={noteOpen} onClose={() => setNoteOpen(false)} problemId={id} onDone={reload} />
      <VideoModal open={videoOpen} onClose={() => setVideoOpen(false)} problemId={id} />
    </div>
  );
}

function TagRow({ label, items }: { label: string; items: { key: string; label: string; to?: string }[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <span className="label">{label}</span>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {items.map((item) =>
          item.to ? (
            <Link key={item.key} to={item.to} className="chip hover:bg-surface-4 hover:text-ink">
              {item.label}
            </Link>
          ) : (
            <span key={item.key} className="chip">
              {item.label}
            </span>
          ),
        )}
      </div>
    </div>
  );
}

function StatusButtons({ problemId, current, onDone }: { problemId: string; current: string; onDone: () => void }) {
  const [setStatus, { pending }] = useAction(api.setStatus);
  const statuses = ['attempted', 'revisit', 'mastered', 'skipped'];

  return (
    <div className="flex flex-wrap gap-2">
      {statuses.map((status) => (
        <button
          key={status}
          disabled={pending || current === status}
          onClick={async () => {
            await setStatus(problemId, status);
            onDone();
          }}
          className={clsx('btn btn-ghost', current === status && 'border-accent text-accent')}
        >
          {status}
        </button>
      ))}
    </div>
  );
}

function SolveModal({
  open,
  onClose,
  problemId,
  mistakeTypes,
  sources,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  problemId: string;
  mistakeTypes: { value: string; label: string }[];
  sources: { value: string; label: string }[];
  onDone: () => void;
}) {
  const [minutes, setMinutes] = useState('');
  const [source, setSource] = useState('independent');
  const [confidence, setConfidence] = useState(3);
  const [attempts, setAttempts] = useState(1);
  const [approach, setApproach] = useState('');
  const [mistakes, setMistakes] = useState<string[]>([]);
  const [result, setResult] = useState<{ xp: number; streak: number; unlocked: string[] } | null>(null);
  const [solve, { pending, error }] = useAction(api.solve);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const outcome = await solve(problemId, {
      solution_source: source,
      time_spent_seconds: minutes ? Number(minutes) * 60 : undefined,
      confidence,
      attempt_count: attempts,
      approach: approach || undefined,
      mistakes,
    });
    if (outcome) {
      setResult({ xp: outcome.xp_awarded, streak: outcome.streak, unlocked: outcome.achievements_unlocked });
      onDone();
    }
  }

  function close() {
    setResult(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={close} title="Record a solve">
      {result ? (
        <div className="px-4 py-6 text-center">
          <div className="text-3xl font-semibold text-accent">+{result.xp} XP</div>
          <p className="mt-1 text-sm text-ink-muted">Streak: {result.streak} days</p>
          {result.unlocked.length > 0 && (
            <p className="mt-2 text-sm text-success">
              Unlocked: {result.unlocked.join(', ')}
            </p>
          )}
          <button onClick={close} className="btn btn-primary mt-4">
            Done
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3.5 px-4 py-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Time spent (min)">
              <input
                type="number"
                min={0}
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                placeholder="e.g. 25"
                className={inputClass}
              />
            </Field>
            <Field label="Attempts">
              <input
                type="number"
                min={1}
                value={attempts}
                onChange={(e) => setAttempts(Number(e.target.value))}
                className={inputClass}
              />
            </Field>
          </div>

          <Field label="How did you solve it?" hint="This drives independence analytics — be honest.">
            <select value={source} onChange={(e) => setSource(e.target.value)} className={inputClass}>
              {sources.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label={`Confidence: ${confidence}/5`}>
            <input
              type="range"
              min={1}
              max={5}
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
              className="w-full accent-[var(--color-accent)]"
            />
          </Field>

          <Field label="Approach (optional)">
            <textarea
              rows={2}
              value={approach}
              onChange={(e) => setApproach(e.target.value)}
              placeholder="Key insight, state definition, invariant…"
              className={inputClass}
            />
          </Field>

          <Field label="Mistakes made (optional)">
            <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
              {mistakeTypes.map((mistake) => {
                const active = mistakes.includes(mistake.value);
                return (
                  <button
                    key={mistake.value}
                    type="button"
                    onClick={() =>
                      setMistakes((prev) =>
                        active ? prev.filter((m) => m !== mistake.value) : [...prev, mistake.value],
                      )
                    }
                    className={clsx('chip', active ? 'bg-danger/20 text-danger' : 'hover:bg-surface-4')}
                  >
                    {mistake.label}
                  </button>
                );
              })}
            </div>
          </Field>

          {error && <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error.message}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={close} className="btn btn-ghost">
              Cancel
            </button>
            <button type="submit" disabled={pending} className="btn btn-primary disabled:opacity-50">
              {pending ? 'Saving…' : 'Record solve'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function NoteModal({ open, onClose, problemId, onDone }: { open: boolean; onClose: () => void; problemId: string; onDone: () => void }) {
  const [kind, setKind] = useState('insight');
  const [content, setContent] = useState('');
  const [addNote, { pending, error }] = useAction(api.addNote);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!content.trim()) return;
    const ok = await addNote(problemId, { kind, content_md: content });
    if (ok !== null) {
      setContent('');
      onDone();
      onClose();
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add a note">
      <form onSubmit={submit} className="space-y-3 px-4 py-4">
        <Field label="Kind">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={inputClass}>
            {['insight', 'approach', 'proof', 'complexity', 'mistake', 'alternative', 'remember'].map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Note (Markdown)">
          <textarea
            autoFocus
            rows={6}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className={inputClass}
            placeholder="What is the one thing you want to remember about this problem?"
          />
        </Field>
        {error && <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error.message}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn btn-ghost">
            Cancel
          </button>
          <button type="submit" disabled={pending || !content.trim()} className="btn btn-primary disabled:opacity-50">
            Save note
          </button>
        </div>
      </form>
    </Modal>
  );
}

function VideoModal({ open, onClose, problemId }: { open: boolean; onClose: () => void; problemId: string }) {
  const { data, loading, error, reload } = useApi(
    () => (open ? api.resources(problemId) : Promise.resolve(null)),
    [open, problemId],
  );
  const [playing, setPlaying] = useState<string | null>(null);

  return (
    <Modal open={open} onClose={onClose} title="Solution videos" wide>
      {loading && <Loading label="Searching trusted channels" />}
      {error && <ErrorState error={error} onRetry={reload} />}

      {data && !data.available && (
        <div className="px-4 py-6">
          <Empty title="Video search unavailable" hint={data.message} icon={<BookOpen size={20} />} />
        </div>
      )}

      {data?.available && data.candidates.length === 0 && (
        <Empty
          title="No matching solution video found"
          hint="Only trusted channels are searched, and nothing matched this problem closely enough."
        />
      )}

      {data?.available && data.candidates.length > 0 && (
        <div className="px-4 py-4">
          {playing && (
            <div className="mb-4 aspect-video w-full overflow-hidden rounded-lg bg-black">
              <iframe
                src={`https://www.youtube-nocookie.com/embed/${playing}`}
                title="Solution video"
                allow="accelerometer; clipboard-write; encrypted-media; picture-in-picture"
                allowFullScreen
                className="h-full w-full"
              />
            </div>
          )}
          <ul className="divide-y divide-line">
            {data.candidates.map((video) => (
              <li key={video.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-sm text-ink">{video.title}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-dim">
                    <span>{video.channel_title}</span>
                    {video.duration_seconds && <span>{Math.round(video.duration_seconds / 60)}m</span>}
                    <span className="font-mono">score {video.score.toFixed(1)}</span>
                    {video.is_selected && <span className="text-accent">best match</span>}
                  </div>
                </div>
                <button onClick={() => setPlaying(video.external_id)} className="btn btn-ghost shrink-0">
                  Play
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
