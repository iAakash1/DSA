/** User collections: Inbox, Favorites, Revision, Mistakes and custom lists. */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { FolderPlus } from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useAction, useApi } from '../hooks/useApi';
import { Card, Empty, ErrorState, Field, Loading, Modal, inputClass } from '../components/ui';
import { problemRef, ratingColor, statusColor } from '../lib/format';

export function Collections() {
  const { slug } = useParams();
  const [active, setActive] = useState(slug ?? 'inbox');
  const [createOpen, setCreateOpen] = useState(false);

  const collections = useApi(() => api.collections(), []);
  const problems = useApi(
    () => (active ? api.problems({ collection: active, limit: 200 }) : Promise.resolve(null)),
    [active],
  );

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Collections</h1>
        <button onClick={() => setCreateOpen(true)} className="btn btn-ghost">
          <FolderPlus size={14} /> New collection
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-1">
          {collections.loading && <Loading />}
          <ul className="space-y-1 px-2 py-2">
            {(collections.data ?? []).map((collection) => (
              <li key={collection.slug}>
                <button
                  onClick={() => setActive(collection.slug)}
                  className={clsx(
                    'flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-sm',
                    active === collection.slug
                      ? 'bg-surface-3 text-ink'
                      : 'text-ink-muted hover:bg-surface-2',
                  )}
                >
                  <span className="flex items-center gap-2">
                    {collection.color && (
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: collection.color }}
                      />
                    )}
                    {collection.name}
                  </span>
                  <span className="tabular text-xs text-ink-dim">{collection.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <div className="lg:col-span-3">
          <Card title={collections.data?.find((c) => c.slug === active)?.name ?? 'Collection'}>
            {problems.loading && <Loading />}
            {problems.error && <ErrorState error={problems.error} onRetry={problems.reload} />}
            {problems.data && problems.data.items.length === 0 && (
              <Empty
                title="This collection is empty"
                hint="Add problems from the problem page, or paste a URL with the Add button."
              />
            )}
            {problems.data && problems.data.items.length > 0 && (
              <ul className="divide-y divide-line">
                {problems.data.items.map((problem) => (
                  <li key={problem.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                    <div className="min-w-0">
                      <Link
                        to={`/problems/${problem.id}`}
                        className="truncate font-medium text-ink hover:text-accent"
                      >
                        {problem.title}
                      </Link>
                      <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-ink-dim">
                        <span>
                          {problemRef(problem)}
                        </span>
                        {problem.rating && (
                          <span className={ratingColor(problem.rating)}>{problem.rating}</span>
                        )}
                      </div>
                    </div>
                    <span className={clsx('shrink-0 text-xs', statusColor(problem.status))}>
                      {problem.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <CreateCollectionModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => collections.reload()}
      />
    </div>
  );
}

function CreateCollectionModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [create, { pending, error }] = useAction(api.createCollection);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    const result = await create({ name: name.trim(), description: description || undefined });
    if (result) {
      setName('');
      setDescription('');
      onCreated();
      onClose();
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New collection">
      <form onSubmit={submit} className="space-y-3 px-4 py-4">
        <Field label="Name">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ICPC Preparation"
            className={inputClass}
          />
        </Field>
        <Field label="Description (optional)">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={inputClass}
          />
        </Field>
        {error && <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error.message}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn btn-ghost">
            Cancel
          </button>
          <button type="submit" disabled={pending || !name.trim()} className="btn btn-primary disabled:opacity-50">
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}
