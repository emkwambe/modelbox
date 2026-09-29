/**
 * The engagement journey runs in CI only (Amendment 1), against the appliance
 * the "Engagement Journey" job starts in configuration B. It needs:
 *
 *   E2E_BASE_URL   the UI's address, e.g. http://localhost:13000
 *   E2E_EMAIL      the owner made by `create-owner`
 *   E2E_PASSWORD   that owner's password (masked in the job)
 *
 * A trace and a screenshot are kept for a failed test and uploaded by the job.
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  // One journey through one appliance: its steps share state, in order.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 10 * 60 * 1000,
  expect: { timeout: 30 * 1000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.E2E_BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1600, height: 1000 },
    acceptDownloads: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 1000 } } }],
});
