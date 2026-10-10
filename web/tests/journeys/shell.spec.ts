import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

/**
 * T17 done-when: "Playwright: navigation reaches every tab; theme switch follows system and
 * override; greeting by local time; en-GB date formats" — on the real stack.
 */

const nav = copy.nav;

test.describe('the app shell (spec 5.1, SET-1, SET-2, TOD-1)', () => {
  test('navigation reaches every tab, and More leads to Settings', async ({ page }) => {
    const email = 'zee.shell@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);
    const bar = page.getByRole('navigation', { name: nav.label });

    await bar.getByRole('link', { name: nav.health }).click();
    await expect(page).toHaveURL(/\/health\/cycle$/);
    await expect(page.getByRole('heading', { level: 1, name: copy.health.title })).toBeVisible();
    await expect(bar.getByRole('link', { name: nav.health })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await bar.getByRole('link', { name: nav.calendar }).click();
    await expect(page.getByRole('heading', { level: 1, name: copy.calendar.title })).toBeVisible();

    await bar.getByRole('link', { name: nav.more }).click();
    await expect(page.getByRole('heading', { level: 1, name: copy.more.title })).toBeVisible();
    await page.getByRole('link', { name: copy.more.settings }).click();
    await expect(
      page.getByRole('heading', { level: 1, name: copy.settingsHome.title }),
    ).toBeVisible();

    await bar.getByRole('button', { name: nav.add }).click();
    await expect(page.getByRole('dialog', { name: copy.quickAdd.title })).toBeVisible();
    await expect(bar).toBeHidden(); // "always visible except in sheets"
    await page.getByRole('button', { name: copy.quickAdd.close }).click();

    await bar.getByRole('link', { name: nav.today }).click();
    await expect(page.getByRole('heading', { level: 1, name: /, Zee$/ })).toBeVisible();
  });

  test('[SET-2] the theme follows the system, and her choice overrides it', async ({ page }) => {
    const email = 'zee.theme@example.test';
    await page.emulateMedia({ colorScheme: 'dark' });
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);
    const html = page.locator('html');
    await expect(html).toHaveAttribute('data-theme', 'dark'); // System (default), phone is dark

    await page.goto('/settings/theme');
    const saved = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/me/settings') && response.ok(),
    );
    await page.getByRole('radio', { name: copy.theme.light }).check({ force: true });
    await expect(html).toHaveAttribute('data-theme', 'light'); // at once
    await saved;
    await page.reload(); // saved to her settings, and remembered on the device
    await expect(html).toHaveAttribute('data-theme', 'light');
    await page.emulateMedia({ colorScheme: 'light' });
    await page.emulateMedia({ colorScheme: 'dark' });
    await expect(html).toHaveAttribute('data-theme', 'light'); // the override ignores the phone

    await page.getByRole('radio', { name: copy.theme.system }).check({ force: true });
    await expect(html).toHaveAttribute('data-theme', 'dark');
    await page.emulateMedia({ colorScheme: 'light' });
    await expect(html).toHaveAttribute('data-theme', 'light'); // and follows it as it changes
  });
});

test.describe('greeting by her local time, dates in en-GB (TOD-1, SET-1)', () => {
  // Her phone is in Tokyo; registration adopts the device timezone (CR-030).
  test.use({ timezoneId: 'Asia/Tokyo' });

  test('[TOD-1] at 08:30 in Tokyo on Friday 9 October she reads "Good morning, Zee"', async ({
    page,
  }) => {
    const email = 'zee.tokyo@example.test';
    await page.clock.setFixedTime(new Date('2026-10-08T23:30:00Z'));
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);
    await page.reload(); // her profile timezone is now Asia/Tokyo
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: copy.today.greetingWithName(copy.today.greeting.morning, 'Zee'),
      }),
    ).toBeVisible();
    await expect(page.getByText('Friday 9 October', { exact: true })).toBeVisible();

    await page.goto('/settings/profile');
    await expect(page.getByLabel(copy.profile.timezone)).toHaveValue('Asia/Tokyo');
  });
});
