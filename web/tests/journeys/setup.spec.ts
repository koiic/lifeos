import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite } from './stack';

const tSetup = copy.setup;
const tMode = copy.healthMode;
const tCycle = copy.health.cycle;

test.describe('setup wizard and health mode settings (spec 3 J1, 5.2, ONB-2, SET-4, MOD-1, MOD-2)', () => {
  test('[ONB-2][SET-4][MOD-1][MOD-2] wizard steps skippable and re-runnable; mode change records start date and hides predictions in postpartum; axe clean', async ({
    page,
  }) => {
    const email = 'zee.setup@example.test';
    await addAuthenticator(page);
    await registerWithPasskey(page, createInvite(email), email);

    // 1. Navigate to /setup/1
    await page.goto('/setup/1');
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step1.title })).toBeVisible();

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

    // Select standard mode and advance
    const standardRadio = page.getByRole('radio', {
      name: new RegExp(tMode.modes.standard.label, 'i'),
    });
    await expect(standardRadio).toBeVisible();
    await standardRadio.check();
    await page.getByRole('button', { name: tSetup.next }).click();

    // 2. Step 2: Last period start date
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step2.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.next }).click();

    // 3. Step 3: Usual cycle and period length
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step3.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.step3.useDefaults }).click();
    await page.getByRole('button', { name: tSetup.next }).click();

    // 4. Step 4: Reminder preferences
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step4.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.finish }).click();

    // Lands on Notifications opt-in
    await expect(
      page.getByRole('heading', { level: 1, name: copy.notifications.title }),
    ).toBeVisible();

    // 5. Re-run wizard from Settings (ONB-2)
    await page.goto('/settings');
    await expect(page.getByRole('link', { name: copy.settingsHome.setupWizard })).toBeVisible();
    await page.getByRole('link', { name: copy.settingsHome.setupWizard }).click();

    // On Step 1: test skipping steps
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step1.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.skip }).click();

    // Step 2: skip
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step2.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.skip }).click();

    // Step 3: skip
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step3.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.skip }).click();

    // Step 4: skip
    await expect(page.getByRole('heading', { level: 1, name: tSetup.step4.title })).toBeVisible();
    await page.getByRole('button', { name: tSetup.skip }).click();

    // 6. Health mode settings screen (SET-4, MOD-2)
    await page.goto('/settings/mode');
    await expect(page.getByRole('heading', { level: 1, name: tMode.title })).toBeVisible();

    // Axe audit on Health mode screen
    const axeMode = await new AxeBuilder({ page }).analyze();
    expect(axeMode.violations).toEqual([]);

    // Select Postpartum recovery
    const postpartumRadio = page.getByRole('radio', {
      name: new RegExp(tMode.modes.postpartum.label, 'i'),
    });
    await postpartumRadio.check();

    // Note appears
    await expect(page.getByRole('note')).toHaveText(tMode.postpartumNote);

    // Save mode
    await page.getByRole('button', { name: tMode.save }).click();
    await expect(page.getByRole('status')).toHaveText(tMode.saved);
    await expect(page.getByText(/Started on/i)).toBeVisible();

    // 7. Verify Postpartum Mode effect on Cycle screen (MOD-2)
    await page.goto('/health/cycle');
    await expect(page.getByText(tCycle.states.waiting).first()).toBeVisible();

    // 8. Switch back to Standard mode (MOD-1)
    await page.goto('/settings/mode');
    const standardRadio2 = page.getByRole('radio', {
      name: new RegExp(tMode.modes.standard.label, 'i'),
    });
    await standardRadio2.check();
    await page.getByRole('button', { name: tMode.save }).click();
    await expect(page.getByRole('status')).toHaveText(tMode.saved);
  });
});
