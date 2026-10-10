import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

test.describe('offline outbox and sync (spec 11.4, 11.5, J9, CHK-5, TOD-7)', () => {
  test('[CHK-5][TOD-7] offline check-in saves locally, shows "Will sync", and syncs once upon reconnect', async ({
    page,
    context,
  }) => {
    const email = 'zee.offline@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // Ensure Today screen is fully loaded
    await page.goto('/today');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // Verify no "Will sync" chip initially
    await expect(page.getByRole('button', { name: copy.today.willSync })).toBeHidden();

    // Go offline (simulating flight mode or loss of signal, J9)
    await context.setOffline(true);

    // Open check-in sheet while offline via client-side routing
    await page.evaluate(() => {
      (
        window as unknown as { lifeosRouter?: { navigate: (path: string) => void } }
      ).lifeosRouter?.navigate('/checkin');
    });
    const sheet = page.getByRole('dialog', { name: copy.checkin.title });
    await expect(sheet).toBeVisible();

    // Select mood: Good (4) and energy: 4
    await sheet.getByRole('radio', { name: copy.checkin.mood.good }).click();
    await sheet.getByRole('radio', { name: '4' }).click();

    // Save check-in while offline
    await sheet.getByRole('button', { name: copy.checkin.save }).click();

    // Sheet closes upon saving to local outbox
    await expect(sheet).toBeHidden();

    // Verify we are back on Today and the "Will sync" chip appears (TOD-7)
    const willSyncChip = page.getByRole('button', { name: copy.today.willSync });
    await expect(willSyncChip).toBeVisible();

    // Restore network connection
    await context.setOffline(false);

    // Click "Will sync" chip or trigger reconnect sync
    const syncPromise = page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/daily-logs/') && res.request().method() === 'PUT' && res.ok(),
    );
    await willSyncChip.click();
    await syncPromise;

    // "Will sync" chip disappears once outbox is drained
    await expect(willSyncChip).toBeHidden();

    // Verify the server received the daily log
    const todayIso = new Date().toISOString().slice(0, 10);
    const logData = await page.evaluate(async (iso) => {
      const res = await fetch(`/api/v1/daily-logs/${iso}`, {
        headers: { 'X-LifeOS-Client': 'web' },
      });
      return res.ok ? await res.json() : null;
    }, todayIso);
    expect(logData).not.toBeNull();
    expect(logData.mood).toBe(4);
    expect(logData.energy).toBe(4);
  });
});
