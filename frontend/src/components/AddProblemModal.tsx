/** Paste a LeetCode/Codeforces URL and add it to the tracker. */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useAction } from '../hooks/useApi';
import { Field, Modal, inputClass } from './ui';

export function AddProblemModal({
  open,
  onClose,
  onAdded,
}: {
  open: boolean;
  onClose: () => void;
  onAdded?: () => void;
}) {
  const navigate = useNavigate();
  const [reference, setReference] = useState('');
  const [collection, setCollection] = useState('inbox');
  const [add, { pending, error }] = useAction(api.addProblem);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!reference.trim()) return;
    const result = await add({ reference: reference.trim(), collection });
    if (result) {
      setReference('');
      onAdded?.();
      onClose();
      navigate(`/problems/${result.id}`);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add a problem">
      <form onSubmit={submit} className="space-y-4 px-4 py-4">
        <Field
          label="Problem URL or ID"
          hint="Accepts a full URL, a Codeforces id like 1400B, or a LeetCode slug."
        >
          <input
            autoFocus
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="https://codeforces.com/problemset/problem/1400/B"
            className={inputClass}
          />
        </Field>

        <Field label="Add to">
          <select
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            className={inputClass}
          >
            <option value="inbox">Inbox</option>
            <option value="favorites">Favorites</option>
            <option value="revision">Revision</option>
            <option value="mistakes">Mistakes</option>
          </select>
        </Field>

        {error && (
          <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error.message}</p>
        )}

        <p className="text-xs text-ink-dim">
          Metadata is fetched from the platform when it is reachable. If it is not, the problem is
          still added and details fill in on the next sync.
        </p>

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn btn-ghost">
            Cancel
          </button>
          <button type="submit" disabled={pending || !reference.trim()} className="btn btn-primary disabled:opacity-50">
            {pending ? 'Adding…' : 'Add problem'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
