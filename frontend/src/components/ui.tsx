/** Shared primitives. Small, unopinionated, used everywhere. */

import { AlertTriangle, Inbox, Loader2, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import clsx from 'clsx';
import type { ApiError } from '../lib/api';

export function Card({
  children,
  className,
  title,
  action,
  subtitle,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className={clsx('card animate-in', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-dim">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function StatTile({
  label,
  value,
  hint,
  accent,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="card card-hover px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        {icon && <span className="text-ink-dim">{icon}</span>}
      </div>
      <div className={clsx('tabular mt-1.5 text-2xl font-semibold', accent ?? 'text-ink')}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-dim">{hint}</div>}
    </div>
  );
}

export function ProgressBar({
  value,
  className,
  barClass = 'bg-accent',
  height = 'h-1.5',
}: {
  value: number;
  className?: string;
  barClass?: string;
  height?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className={clsx('w-full overflow-hidden rounded-full bg-surface-3', height, className)}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={clsx('h-full rounded-full transition-[width] duration-500', barClass)} style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx('chip', className)}>{children}</span>;
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-4 py-10 text-sm text-ink-dim">
      <Loader2 size={15} className="animate-spin" />
      {label}…
    </div>
  );
}

export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
      <div className="mb-2 text-ink-dim">{icon ?? <Inbox size={22} />}</div>
      <p className="text-sm font-medium text-ink-muted">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-xs text-ink-dim">{hint}</p>}
    </div>
  );
}

/**
 * Error states name the failing subsystem and reassure about data, rather than
 * showing a bare status code.
 */
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      <AlertTriangle size={20} className="mb-2 text-danger" />
      <p className="text-sm font-medium text-ink">{error.message}</p>
      {error.details?.last_success ? (
        <p className="mt-1 text-xs text-ink-dim">
          Your data is safe. Last successful sync: {String(error.details.last_success)}
        </p>
      ) : (
        <p className="mt-1 text-xs text-ink-dim">Your existing data is unaffected.</p>
      )}
      {onRetry && (
        <button className="btn btn-ghost mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 pt-[8vh] backdrop-blur-sm">
      <div
        className="absolute inset-0"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          'card animate-in relative w-full overflow-hidden',
          wide ? 'max-w-4xl' : 'max-w-lg',
        )}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button onClick={onClose} className="text-ink-dim hover:text-ink" aria-label="Close">
            <X size={16} />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <p className="mt-1 text-xs text-ink-dim">{hint}</p>}
    </label>
  );
}

/**
 * Width-free base. Tailwind cannot resolve `w-full` vs `w-auto` by class-string
 * order — they have equal specificity — so width is always supplied by the
 * caller rather than baked in and overridden.
 */
export const inputBase =
  'rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-dim focus:border-accent focus:outline-none';

export const inputClass = `${inputBase} w-full`;
