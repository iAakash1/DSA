/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Present once Clerk is configured; enables authenticated mode. */
  readonly VITE_CLERK_PUBLISHABLE_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
