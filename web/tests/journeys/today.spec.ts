import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

test.describe('today check-in card and streak badge (spec 4.3, 5.2, 5.6, 9.3, J3, TOD-3, TOD-5)', () => {
  test('[TOD-3][TOD-5] uncompleted card on Today, check-in from mood button, completed state with summary, streak badge from 3 days; axe clean in both themes', async ({
    page,
  }) => {
    const email = 'zee.today@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // 1. Navigate to Today screen
    await page.goto('/today');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // Verify uncompleted check-in card
    const checkinHeading = page.getByRole('heading', {
      level: 2,
      name: copy.today.checkinCard.title,
    });
    await expect(checkinHeading).toBeVisible();

    await expect(page.getByText(copy.today.checkinCard.prompt)).toBeVisible();

    // 5 mood buttons are visible
    const goodMoodBtn = page.getByRole('button', { name: copy.checkin.mood.good });
    await expect(goodMoodBtn).toBeVisible();

    // Streak badge is NOT visible initially (streak < 3)
    await expect(page.getByTestId('streak-badge')).toBeHidden();

    // Axe audit in Sorbet (light theme)
    await page.evaluate(() => document.fonts.ready);
    const axeLight = await new AxeBuilder({ page }).analyze();
    expect(axeLight.violations).toEqual([]);

    // Axe audit in Night Garden (dark theme)
    await page.locator('html').evaluate((el) => el.setAttribute('data-theme', 'dark'));
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    const axeDark = await new AxeBuilder({ page }).analyze();
    expect(axeDark.violations).toEqual([]);

    // Restore light theme
    await page.locator('html').evaluate((el) => el.removeAttribute('data-theme'));

    // 2. Tap mood button "Good" to start check-in with pre-selected mood
    await goodMoodBtn.click();

    // Sheet opens for check-in
    const sheet = page.getByRole('dialog', { name: copy.checkin.title });
    await expect(sheet).toBeVisible();

    // Verify mood "Good" is pre-selected
    await expect(page.getByRole('radio', { name: copy.checkin.mood.good })).toHaveAttribute(
      'aria-checked',
      'true',
    );

    // Adjust energy and sleep
    await page.getByRole('radio', { name: '4' }).click();
    await page.getByRole('button', { name: copy.checkin.sleep.increase }).click();

    // Save check-in
    const savePromise = page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/daily-logs/') && res.request().method() === 'PUT' && res.ok(),
    );
    await sheet.getByRole('button', { name: copy.checkin.save }).click();
    await savePromise;

    // Sheet closes and we are back on Today
    await expect(sheet).toBeHidden();

    // 3. Today screen now shows completed state
    const doneHeading = page.getByRole('heading', {
      level: 2,
      name: copy.today.checkinCard.doneTitle,
    });
    await expect(doneHeading).toBeVisible();
    await expect(page.getByTestId('completed-sticker')).toBeVisible();

    // Summary items are visible
    await expect(page.getByTestId('summary-mood')).toContainText(copy.checkin.mood.good);
    await expect(page.getByTestId('summary-energy')).toContainText('4/5');
    await expect(page.getByTestId('summary-sleep')).toContainText('7.5 hrs');

    // Edit link is available
    const editBtn = page.getByRole('button', { name: copy.today.checkinCard.edit });
    await expect(editBtn).toBeVisible();

    // 4. Back-fill 2 previous days via API to achieve 3-day streak
    const backfillOk = await page.evaluate(async () => {
      const todayRes = await fetch('/api/v1/today');
      const todayData = await todayRes.json();

      const [year, month, day] = todayData.date.split('-').map(Number);
      const curr = new Date(Date.UTC(year, month - 1, day));

      for (let i = 1; i <= 2; i++) {
        const past = new Date(curr.getTime() - i * 86400000);
        const pastDateStr = past.toISOString().slice(0, 10);
        const res = await fetch(`/api/v1/daily-logs/${pastDateStr}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'X-LifeOS-Client': 'web',
          },
          body: JSON.stringify({
            mood: 4,
            energy: 3,
            flow: 'none',
            symptom_ids: [],
            client_updated_at: new Date().toISOString(),
          }),
        });
        if (!res.ok) return false;
      }

      // Clear persisted query cache so reload fetches fresh state from server
      await new Promise((resolve) => {
        const req = indexedDB.open('lifeos_offline');
        req.onsuccess = () => {
          const db = req.result;
          if (db.objectStoreNames.contains('query_cache')) {
            const tx = db.transaction('query_cache', 'readwrite');
            tx.objectStore('query_cache').clear();
            tx.oncomplete = () => resolve(true);
            tx.onerror = () => resolve(false);
          } else {
            resolve(true);
          }
        };
        req.onerror = () => resolve(false);
      });

      return true;
    });
    expect(backfillOk).toBe(true);

    // Reload Today screen to refresh streak
    await page.reload();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // 5. Streak badge is now visible with 3-day streak
    const streakBadge = page.getByTestId('streak-badge');
    await expect(streakBadge).toBeVisible();
    await expect(streakBadge).toContainText(copy.today.streak(3));

    // Final axe check with streak badge and completed card
    const axeFinal = await new AxeBuilder({ page }).analyze();
    expect(axeFinal.violations).toEqual([]);
  });
});
