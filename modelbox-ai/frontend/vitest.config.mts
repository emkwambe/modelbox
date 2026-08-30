import react from '@vitejs/plugin-react';
import tsconfigPaths from 'vite-tsconfig-paths';
import { defineConfig } from 'vitest/config';

/**
 * The frontend had no test runner at all before Sprint 6, which is why criteria
 * F2, F3, F4 and F6 had no possible evidence — every one of them is a statement
 * about rendered behaviour or computed colour.
 *
 * jsdom rather than a browser: the suite has to be fast enough to be a required
 * CI job. Its limit is stated where it matters — jsdom cannot measure layout,
 * so the canvas tests prove the *re-render* defect is fixed, not that the canvas
 * is usable at scale. That second claim rests on the profiling script and must
 * not be read off these tests.
 */
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  // Next's tsconfig sets `jsx: preserve` because Next does the transform. The
  // test runner has to do it instead, and without this JSX compiles to
  // `React.createElement` against a `React` that was never imported.
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
