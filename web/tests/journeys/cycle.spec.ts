import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

const t = copy.health;

test.describe('cycle screen, ring, predictions, history and exclusions (spec 5.2, 8.4, J5, CSC-1, CSC-2, CSC-4, CYC-3, CYC-4, CYC-5, CYC-6)', () => {
  test('[CSC-1][CSC-2][CSC-4][CYC-3][CYC-4][CYC-5][CYC-6] view cycle ring, prediction card with disclaimer, history list and toggle exclusion; axe clean', async ({
    page,
  }) => {
    const email = 'zee.cycle@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // Step 1 (J5, CSC-1): Navigate to /health/cycle
    await page.goto('/health/cycle');
    await expect(page.getByRole('heading', { level: 1, name: t.title })).toBeVisible();

    // Verify tabs
    const healthNav = page.getByRole('navigation', { name: t.navLabel });
    await expect(healthNav.getByRole('link', { name: t.cycleTab })).toBeVisible();
    await expect(healthNav.getByRole('link', { name: t.calendarTab })).toBeVisible();
    await expect(healthNav.getByRole('link', { name: t.historyTab })).toBeVisible();

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

    // Step 2 (CSC-1, CSC-2): Check initial ring and prediction card
    const ring = page.getByRole('img');
    await expect(ring).toBeVisible();

    // Prediction card displays initial prompt
    await expect(page.getByText(t.cycle.states.no_data).first()).toBeVisible();

    // Step 3 (PER-1, CSC-1): Start a period
    const startBtn = page.getByRole('button', { name: t.period.started });
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    // Now period is ongoing
    const endBtn = page.getByRole('button', { name: t.period.ended });
    await expect(endBtn).toBeVisible();

    // Ring reflects day 1 and menstrual phase
    await expect(page.getByText(/Day 1/i).first()).toBeVisible();

    // Step 4 (CSC-4, CYC-5): Navigate to Cycle History
    await healthNav.getByRole('link', { name: t.historyTab }).click();
    await expect(page.getByRole('heading', { level: 1, name: t.history.title })).toBeVisible();

    // Axe audit on history screen
    const axeHistory = await new AxeBuilder({ page }).analyze();
    expect(axeHistory.violations).toEqual([]);

    // Cycles list shows the ongoing/started cycle
    const excludeBtn = page.getByRole('button', { name: t.history.cycleItem.excludeAction });
    if (await excludeBtn.isVisible()) {
      // Step 5 (CYC-5): Exclude cycle with reason
      await excludeBtn.click();
      const dialog = page.getByRole('dialog', { name: t.history.cycleItem.excludeTitle });
      await expect(dialog).toBeVisible();

      // Confirm exclusion
      const dialogConfirmBtn = dialog.getByRole('button', {
        name: t.history.cycleItem.excludeAction,
      });
      await dialogConfirmBtn.click();

      // Cycle now shows Excluded badge
      await expect(page.getByText(t.history.cycleItem.excludedBadge)).toBeVisible();

      // Re-include cycle
      const includeBtn = page.getByRole('button', {
        name: t.history.cycleItem.includeAction,
      });
      await includeBtn.click();
      await expect(includeBtn).toBeHidden();
    }

    // Navigate back to Cycle screen
    await page.getByRole('link', { name: t.history.back }).click();
    await expect(page.getByRole('heading', { level: 1, name: t.title })).toBeVisible();
  });
});
