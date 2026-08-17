/** Thin data-fetching hooks. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../lib/api';

interface State<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
}

/**
 * Fetch on mount and whenever `deps` change.
 *
 * Errors are captured into state rather than thrown, because a failing panel
 * must never take down the page around it.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): State<T> & { reload: () => void } {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null });
  const [nonce, setNonce] = useState(0);
  const alive = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    alive.current = true;
    setState((prev) => ({ ...prev, loading: true }));

    fetcherRef
      .current()
      .then((data) => {
        if (alive.current) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!alive.current) return;
        const apiError =
          error instanceof ApiError ? error : new ApiError(0, 'unknown', String(error));
        setState({ data: null, loading: false, error: apiError });
      });

    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}

/** For POST/PATCH actions with pending + error state. */
export function useAction<Args extends unknown[], R>(
  action: (...args: Args) => Promise<R>,
): [(...args: Args) => Promise<R | null>, { pending: boolean; error: ApiError | null }] {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const run = useCallback(
    async (...args: Args) => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (err: unknown) {
        setError(err instanceof ApiError ? err : new ApiError(0, 'unknown', String(err)));
        return null;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return [run, { pending, error }];
}

/** Global keyboard shortcuts. Ignored while typing in an input. */
export function useHotkeys(bindings: Record<string, () => void>) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable);

      const combo = [
        event.metaKey || event.ctrlKey ? 'mod' : '',
        event.key.toLowerCase(),
      ]
        .filter(Boolean)
        .join('+');

      const handler = bindings[combo];
      if (!handler) return;
      // Modifier combos still fire while typing; bare letters do not.
      if (typing && !combo.startsWith('mod')) return;

      event.preventDefault();
      handler();
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [bindings]);
}
