/**
 * The unauthenticated entry point.
 *
 * A signed-out visitor must always have something obvious to click. Clerk's
 * `<SignIn>` is mounted directly rather than behind a redirect, so there is no
 * intermediate state where the page has rendered but the way in has not.
 * The two buttons switch between Clerk's own sign-in and sign-up flows.
 */

import { useState } from 'react';
import { SignIn, SignUp } from '@clerk/react';
import { BarChart3, Flag, Layers, Zap } from 'lucide-react';

/** Clerk's components, restyled to CP-Forge's dark palette. */
export const CLERK_APPEARANCE = {
  variables: {
    colorBackground: '#12141a',
    colorInputBackground: '#1a1d26',
    colorText: '#e6e8ef',
    colorTextSecondary: '#8b93a7',
    colorPrimary: '#f5b544',
    colorInputText: '#e6e8ef',
    colorNeutral: '#e6e8ef',
    borderRadius: '0.5rem',
    fontFamily: 'inherit',
  },
  elements: {
    rootBox: 'w-full',
    cardBox: 'w-full shadow-none',
    card: 'bg-surface border border-line shadow-none',
    headerTitle: 'text-ink',
    headerSubtitle: 'text-ink-dim',
    socialButtonsBlockButton: 'border-line text-ink hover:bg-surface-2',
    dividerLine: 'bg-line',
    dividerText: 'text-ink-dim',
    formFieldLabel: 'text-ink-dim',
    formButtonPrimary: 'bg-accent text-black hover:bg-accent/90 normal-case',
    footerActionLink: 'text-accent hover:text-accent',
    footer: 'bg-transparent',
  },
} as const;

const HIGHLIGHTS = [
  { icon: Layers, title: '827 curated problems', body: 'CP-31 and the complete Striver A2Z sheet, deduplicated to one canonical problem each.' },
  { icon: BarChart3, title: 'Evidence-based analytics', body: 'Mastery, weaknesses and readiness computed from your own solve history — never estimated.' },
  { icon: Flag, title: 'ICPC mode', body: 'A 25-topic roadmap, 23 compiled C++ templates and timed virtual contests.' },
];

export function SignInScreen() {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');

  return (
    <main className="min-h-screen bg-surface-0 px-4 py-10 lg:px-8">
      <div className="mx-auto grid w-full max-w-5xl items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <section className="order-2 lg:order-1">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-black">
              <Zap size={18} aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-lg font-semibold text-ink">CP-Forge</h1>
              <p className="text-xs text-ink-dim">Competitive programming preparation</p>
            </div>
          </div>

          <p className="mt-5 max-w-md text-sm leading-relaxed text-ink-muted">
            One workspace for your problem sheets, solve history and contest
            preparation — with statistics you can trace back to the work that
            produced them.
          </p>

          <ul className="mt-6 space-y-4">
            {HIGHLIGHTS.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex gap-3">
                <Icon size={15} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
                <div>
                  <h2 className="text-xs font-semibold text-ink">{title}</h2>
                  <p className="mt-0.5 text-xs leading-relaxed text-ink-dim">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="order-1 lg:order-2">
          <div
            role="tablist"
            aria-label="Authentication"
            className="mx-auto mb-4 flex w-full max-w-sm gap-1 rounded-lg border border-line bg-surface p-1"
          >
            {(
              [
                ['sign-in', 'Sign in'],
                ['sign-up', 'Create account'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                role="tab"
                type="button"
                aria-selected={mode === value}
                onClick={() => setMode(value)}
                className={
                  'flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ' +
                  (mode === value
                    ? 'bg-surface-2 text-ink'
                    : 'text-ink-dim hover:text-ink')
                }
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mx-auto w-full max-w-sm">
            {mode === 'sign-in' ? (
              <SignIn
                appearance={CLERK_APPEARANCE}
                routing="hash"
                signUpUrl="#/sign-up"
                fallbackRedirectUrl="/"
              />
            ) : (
              <SignUp
                appearance={CLERK_APPEARANCE}
                routing="hash"
                signInUrl="#/sign-in"
                fallbackRedirectUrl="/"
              />
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

/**
 * Shown when a production build has no Clerk key.
 *
 * Previously this state silently fell back to local mode: the shell rendered,
 * every request 401'd, and the visitor got an error with nothing to click.
 * Naming the cause is more useful to whoever can fix it, and honest to
 * everyone else.
 */
export function AuthUnavailableScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="card max-w-md px-5 py-6 text-center">
        <h1 className="text-base font-semibold text-ink">Sign-in is unavailable</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          CP-Forge cannot reach its authentication provider, so there is no way
          to sign in right now. This is a server configuration problem, not
          something you can fix — please try again later.
        </p>
        <p className="mt-3 border-t border-line pt-3 text-left text-[11px] leading-relaxed text-ink-dim">
          <strong className="text-ink-muted">For the operator:</strong> this
          build has no <code>VITE_CLERK_PUBLISHABLE_KEY</code>. Set it in the
          hosting environment and redeploy — Vite inlines it at build time, so
          a restart alone will not pick it up.
        </p>
      </div>
    </main>
  );
}
