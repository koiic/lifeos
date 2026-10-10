import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

test.describe('cycle calendar and period logging (spec 4.5, 4.8, 5.2, J4, CSC-3, PER-1, PER-3)', () => {
  test('[CSC-3][PER-1][PER-3] logs period start, daily flow, end; edits past day; calendar updates; axe clean', async ({
    page,
  }) => {
    const email = 'zee.calendar@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // Navigate to Cycle Calendar
    await page.goto('/health/calendar');
    await expect(
      page.getByRole('heading', { level: 1, name: copy.health.calendar.title }),
    ).toBeVisible();

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

    // Step 1 (PER-1, J4): Tap "Period started"
    const startBtn = page.getByRole('button', { name: copy.health.period.started });
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    // Now period is ongoing, so "Period ended" button appears
    const endBtn = page.getByRole('button', { name: copy.health.period.ended });
    await expect(endBtn).toBeVisible();

    // Verify today's cell on the calendar has period indicator
    const today = new Date();
    const todayDayNum = today.getDate();
    const todayMonthStr = String(today.getMonth() + 1).padStart(2, '0');
    const todayDateIso = `${today.getFullYear()}-${todayMonthStr}-${String(todayDayNum).padStart(2, '0')}`;
    const todayBtn = page.locator(`button[data-date="${todayDateIso}"]`);
    await expect(todayBtn).toHaveAttribute('data-period', 'true');

    // Step 2 (PER-3, J4): Edit a past day within the same month
    // If today is day 1, pick day 2 or day 1; otherwise pick earlier day in month
    const targetDayNum = todayDayNum > 1 ? todayDayNum - 1 : todayDayNum;
    const targetDateIso = `${today.getFullYear()}-${todayMonthStr}-${String(targetDayNum).padStart(2, '0')}`;
    const targetDayBtn = page.locator(`button[data-date="${targetDateIso}"]`);
    await targetDayBtn.click();

    // Check-in sheet opens for that day
    const sheet = page.getByRole('dialog', { name: copy.checkin.title });
    await expect(sheet).toBeVisible();

    // Set flow to Light and save
    await sheet.getByRole('radio', { name: copy.checkin.flow.light }).check({ force: true });
    await sheet.getByRole('button', { name: copy.checkin.save }).click();
    await expect(sheet).toBeHidden();

    // Calendar updates: target day now has period indicator
    await expect(targetDayBtn).toHaveAttribute('data-period', 'true');

    // Step 3 (PER-1, J4): Tap "Period ended"
    await endBtn.click();
    await expect(startBtn).toBeVisible();
  });
});
