/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The repository keeps one `.env` at its root, shared with the backend.
  // Vite would otherwise only look inside `frontend/`, so VITE_* variables
  // would silently resolve to undefined — and Clerk would look "unconfigured"
  // with the key sitting right there. Only VITE_-prefixed keys are exposed to
  // the browser, so the backend's secrets in the same file stay server-side.
  envDir: path.resolve(__dirname, '..'),
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    rollupOptions: {
      output: {
        // One 800 kB chunk means every deploy re-downloads the charting and
        // auth libraries even when only app code changed. Splitting the three
        // large, rarely-changing dependencies lets them stay cached across
        // releases.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          clerk: ['@clerk/react'],
          charts: ['recharts'],
        },
      },
    },
  },
  server: {
    port: 5173,
    // The browser talks to FastAPI through this proxy, so the frontend never
    // needs to know the backend origin and there is no CORS in development.
    proxy: {
      '/api': {
        // Override with VITE_API_TARGET if port 8010 is taken on your machine.
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
});
