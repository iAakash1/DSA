/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
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
