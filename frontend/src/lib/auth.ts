/**
 * Authentication abstraction.
 *
 * Identity is owned by an external provider (Clerk, once its keys exist).
 * Nothing in the app imports a provider SDK directly — everything goes through
 * this module, so switching providers is one file.
 *
 * Until a provider is configured the app runs in `local` mode: the backend's
 * AUTH_MODE=local resolves a fixed development identity, so every feature works
 * end to end without signing in. That is a deliberate development affordance,
 * not a security bypass — the backend still derives the user id itself and
 * never trusts one supplied by the client.
 */

export type AuthMode = 'local' | 'clerk';

const clerkKey = (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim();

/** The browser-safe Clerk key. The secret key never reaches this bundle. */
export const clerkPublishableKey = clerkKey || undefined;

export const authMode: AuthMode = clerkKey ? 'clerk' : 'local';
export const isAuthConfigured = authMode !== 'local';

/**
 * Token getter used by the API client on every request.
 *
 * `components/AuthGate` registers Clerk's `getToken` here once Clerk has
 * loaded. It is called per request rather than cached because Clerk rotates
 * the session token on a short interval.
 */
let tokenProvider: (() => Promise<string | null>) | null = null;

export function setTokenProvider(provider: (() => Promise<string | null>) | null) {
  tokenProvider = provider;
}

export async function getAccessToken(): Promise<string | null> {
  if (!tokenProvider) return null;
  try {
    return await tokenProvider();
  } catch {
    return null;
  }
}

export interface SessionUser {
  id: string;
  username: string;
  displayName: string | null;
}

/** Local-mode identity, mirroring the backend's development user. */
export const LOCAL_USER: SessionUser = {
  id: '00000000-0000-4000-8000-000000000001',
  username: 'local',
  displayName: 'Local session',
};
