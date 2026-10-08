import { defineConfig, devices } from '@playwright/test';

/**
 * Plan 5.3 rule 4: visual snapshots of every Ladle story in both themes at 390 px wide, plus axe
 * on each (spec 15.1). The suite runs against Ladle's production build, served locally.
 * Later tasks add their journeys (J1–J10) as further projects.
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
  use: { baseURL: 'http://127.0.0.1:61001', locale: 'en-GB', timezoneId: 'Europe/London' },
  projects: [
    {
      name: 'stories',
      testMatch: 'visual/**/*.spec.ts',
      use: { ...devices['Desktop Chrome'], viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    // `npm run test:e2e` builds the stories first (ladle build).
    command: 'npx ladle preview --host 127.0.0.1',
    url: 'http://127.0.0.1:61001/meta.json',
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
