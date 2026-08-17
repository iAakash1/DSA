/**
 * The signed-in user's avatar and sign-out control.
 *
 * Renders nothing in local mode, where there is no session to end — the header
 * should not offer a sign-out that cannot do anything.
 *
 * The post-sign-out destination is set once on ClerkProvider (v6 moved it off
 * this component), so it stays consistent wherever sign-out is triggered.
 */

import { UserButton } from '@clerk/react';
import { authMode } from '../lib/auth';

export function UserMenu() {
  if (authMode === 'local') return null;

  return (
    <UserButton
      appearance={{
        elements: {
          avatarBox: 'h-7 w-7',
          userButtonPopoverCard: 'bg-surface border border-line',
          userButtonPopoverActionButtonText: 'text-ink',
          userButtonPopoverFooter: 'hidden',
        },
      }}
    />
  );
}
