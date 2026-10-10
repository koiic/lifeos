import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

test.describe('daily check-in (spec 4.4, 5.2, J3, CHK-1, CHK-3, CHK-4, PER-2)', () => {
  test('[CHK-1][CHK-3][PER-2] completes check-in in one sheet; axe clean in both themes', async ({
    page,
  }) => {
    const email = 'zee.checkin@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // Open check-in sheet directly (as tapping the daily notification would do, J3 step 1)
    await page.goto('/checkin');

    const sheet = page.getByRole('dialog', { name: copy.checkin.title });
    await expect(sheet).toBeVisible();

    // CHK-4: Optional health tracking is hidden by default
    await expect(page.getByText(copy.checkin.optional.title)).toBeHidden();

    // Axe audit in Sorbet (light theme)
    await page.evaluate(() => document.fonts.ready);
    const axeLight = await new AxeBuilder({ page }).analyze();
    expect(axeLight.violations).toEqual([]);

    // Axe audit in Night Garden (dark theme)
    await page.locator('html').evaluate((el) => el.setAttribute('data-theme', 'dark'));
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    const axeDark = await new AxeBuilder({ page }).analyze();
    expect(axeDark.violations).toEqual([]);

    // Restore light theme for the remainder of the test
    await page.locator('html').evaluate((el) => el.removeAttribute('data-theme'));

    // Step 2: Tap mood: Good (4)
    await page.getByRole('radio', { name: copy.checkin.mood.good }).click();
    await expect(page.getByRole('radio', { name: copy.checkin.mood.good })).toHaveAttribute(
      'aria-checked',
      'true',
    );

    // Tap energy: 4
    await page.getByRole('radio', { name: '4' }).click();
    await expect(page.getByRole('radio', { name: '4' })).toHaveAttribute('aria-checked', 'true');

    // Adjust sleep: click increase (+)
    await page.getByRole('button', { name: copy.checkin.sleep.increase }).click();
    await expect(page.getByText('7.5 hrs')).toBeVisible();

    // Tap flow: Light
    await page.getByRole('radio', { name: copy.checkin.flow.light }).check({ force: true });
    await expect(page.getByRole('radio', { name: copy.checkin.flow.light })).toBeChecked();

    // Select a seeded symptom (e.g. Cramps)
    const crampsChip = page.getByRole('button', { name: /cramps/i });
    if (await crampsChip.isVisible()) {
      await crampsChip.click();
      await expect(crampsChip).toHaveAttribute('aria-pressed', 'true');
    }

    // Add a custom symptom
    await sheet.getByRole('button', { name: copy.checkin.symptoms.addCustom }).click();
    await sheet.getByLabel(copy.checkin.symptoms.nameLabel).fill('Brain fog');
    await sheet.getByRole('button', { name: copy.checkin.symptoms.create, exact: true }).click();
    const brainFogChip = sheet.getByRole('button', { name: /brain fog/i });
    await expect(brainFogChip).toBeVisible();
    await expect(brainFogChip).toHaveAttribute('aria-pressed', 'true');

    // Fill note
    await sheet
      .getByLabel(copy.checkin.note.label)
      .fill('Feeling steady today after a good sleep.');
    await expect(sheet.getByText(/characters left/i)).toBeVisible();

    // Step 3: Save check-in
    const savePromise = page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/daily-logs/') && res.request().method() === 'PUT' && res.ok(),
    );
    await sheet.getByRole('button', { name: copy.checkin.save }).click();
    const response = await savePromise;
    const body = await response.json();

    expect(body.mood).toBe(4);
    expect(body.energy).toBe(4);
    expect(body.sleep_hours).toBe(7.5);
    expect(body.flow).toBe('light');
    expect(body.checkin_ms).toBeGreaterThanOrEqual(0);
    expect(body.note).toBe('Feeling steady today after a good sleep.');

    // Sheet closes upon save
    await expect(sheet).toBeHidden();
  });

  test('[CHK-4] optional fields appear when enabled in user settings', async ({ page }) => {
    const email = 'zee.optional@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // Fetch user settings and update optional_fields to true
    const patchOk = await page.evaluate(async () => {
      const meRes = await fetch('/api/v1/me');
      const meData = await meRes.json();
      const res = await fetch('/api/v1/me/settings', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-LifeOS-Client': 'web',
          'If-Match': `"${meData.settings.version}"`,
        },
        body: JSON.stringify({
          optional_fields: {
            bbt: true,
            discharge: true,
            intimacy: true,
          },
        }),
      });
      return res.ok;
    });
    expect(patchOk).toBe(true);

    // Navigate to check-in sheet
    await page.goto('/checkin');
    const sheet = page.getByRole('dialog', { name: copy.checkin.title });
    await expect(sheet).toBeVisible();

    // Verify optional fields section and fields are visible
    await expect(page.getByText(copy.checkin.optional.title)).toBeVisible();
    await expect(page.getByLabel(new RegExp(copy.checkin.optional.bbt.label, 'i'))).toBeVisible();
    await expect(page.getByLabel(copy.checkin.optional.discharge.label)).toBeVisible();
    await expect(
      page.getByRole('switch', { name: copy.checkin.optional.intimacy.hadSex }),
    ).toBeVisible();
  });
});
