/**
 * Clerk integration, confined to one component.
 *
 * The rest of the app knows nothing about Clerk: it calls `getAccessToken()`
 * from `lib/auth`, and this component is what puts Clerk's `getToken` behind
 * that. Swapping providers stays a two-file change.
 *
 * In local mode (no publishable key) this renders its children directly, so
 * development without a provider keeps working exactly as before.
 */

import { useEffect, type ReactNode } from 'react';
import { ClerkProvider, SignIn, useAuth } from '@clerk/react';
import { Loader2, Zap } from 'lucide-react';
import { authMode, clerkPublishableKey, setTokenProvider } from '../lib/auth';

/** Dark theme for Clerk's own components, so sign-in still looks like CP-Forge. */
const CLERK_APPEARANCE = {
  variables: {
    colorBackground: '#12141a',
    colorInputBackground: '#1a1d26',
    colorText: '#e6e8ef',
    colorTextSecondary: '#8b93a7',
    colorPrimary: '#f5b544',
    colorInputText: '#e6e8ef',
    borderRadius: '0.5rem',
    fontFamily: 'inherit',
  },
  elements: {
    card: 'bg-surface border border-line shadow-none',
    headerTitle: 'text-ink',
    headerSubtitle: 'text-ink-dim',
    socialButtonsBlockButton: 'border-line text-ink',
    footerActionLink: 'text-accent hover:text-accent',
  },
} as const;

function Splash({ label }: { label: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center gap-2 text-sm text-ink-dim">
      <Loader2 size={16} className="animate-spin" />
      {label}
    </div>
  );
}

/**
 * Decides what the session allows, and bridges its token to the API client.
 *
 * The token is registered as a getter rather than read once: Clerk rotates the
 * session token on a short interval, so the API client has to ask for a fresh
 * one per request instead of caching the first.
 *
 * Clerk v6 dropped `<SignedIn>`/`<SignedOut>` in favour of `<Show>`; `useAuth`
 * covers both the gate and the token in one subscription.
 */
function Session({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  // Registered during render rather than in an effect, and deliberately so:
  // React runs child effects *before* parent effects, so an effect here would
  // fire only after the first page had already issued its requests — with no
  // Authorization header. The result was a signed-in user staring at "Sign in
  // to continue". Assigning to a module singleton during render is idempotent
  // and safe under StrictMode's double render.
  if (isSignedIn) {
    setTokenProvider(() => getToken());
  } else if (isLoaded) {
    setTokenProvider(null);
  }

  useEffect(() => () => setTokenProvider(null), []);

  if (!isLoaded) return <Splash label="Starting CP-Forge" />;
  if (!isSignedIn) return <SignInScreen />;
  return <>{children}</>;
}

function SignInScreen() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-black">
          <Zap size={18} />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-ink">CP-Forge</h1>
          <p className="text-xs text-ink-dim">Competitive programming preparation</p>
        </div>
      </div>
      <SignIn
        appearance={CLERK_APPEARANCE}
        routing="hash"
        signUpUrl="#/sign-up"
        fallbackRedirectUrl="/"
      />
    </div>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  if (authMode === 'local') return <>{children}</>;

  return (
    <ClerkProvider
      publishableKey={clerkPublishableKey!}
      appearance={CLERK_APPEARANCE}
      afterSignOutUrl="/"
    >
      <Session>{children}</Session>
    </ClerkProvider>
  );
}
