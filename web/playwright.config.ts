import { defineConfig, devices } from '@playwright/test';

import { API_PORT, STACK_ENV, STACK_SCRIPT, WEB_ORIGIN, WEB_PORT } from './tests/journeys/stack';

/**
 * Plan 5.3 rule 4: visual snapshots of every Ladle story in both themes at 390 px wide, plus axe
 * on each (spec 15.1), against Ladle's production build. Plan 6.1: the journeys (J1–J10, spec
 * 15.1) run in Chromium with a virtual WebAuthn authenticator against a local stack — the API on
 * a fresh database and the built app (tests/journeys/stack.ts). `npm run test:e2e` builds both.
 */
export default defineConfig({
  testDir: 'tests',
  testMatch: '**/*.spec.ts',
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  reporter: [['list']],
  snapshotPathTemplate: '{testDir}/{testFileDir}/__snapshots__/{arg}{ext}',
  expect: {
    toHaveScreenshot: { maxDiffPixels: 0, threshold: 0, animations: 'disabled', caret: 'hide' },
  },
  // Spec: UK English, Europe/London (dates and times render as Zee sees them).
  use: { locale: 'en-GB', timezoneId: 'Europe/London' },
  projects: [
    {
      name: 'stories',
      testMatch: 'visual/**/*.spec.ts',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://127.0.0.1:61001',
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: 'journeys',
      testMatch: 'journeys/**/*.spec.ts',
      use: { ...devices['Pixel 7'], baseURL: WEB_ORIGIN },
    },
  ],
  webServer: [
    {
      command: 'npx ladle preview --host 127.0.0.1',
      url: 'http://127.0.0.1:61001/meta.json',
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `bash ${STACK_SCRIPT}`,
      url: `http://127.0.0.1:${String(API_PORT)}/api/v1/healthz`,
      // DATABASE_URL (if set, e.g. CI) stays the base database; the script makes the e2e one.
      env: {
        APP_ORIGIN: STACK_ENV.APP_ORIGIN,
        E2E_DATABASE_URL: STACK_ENV.DATABASE_URL,
        API_PORT: String(API_PORT),
      },
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `npx vite preview --host localhost --port ${String(WEB_PORT)} --strictPort`,
      url: WEB_ORIGIN,
      env: { LIFEOS_API: `http://127.0.0.1:${String(API_PORT)}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
