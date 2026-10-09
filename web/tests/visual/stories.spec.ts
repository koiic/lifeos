import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

/**
 * Plan 5.3 rules 2-4: every Ladle story in Sorbet and Night Garden at 390 px matches its snapshot
 * and has no axe violations. The story list is Ladle's own metadata, so a new story is covered
 * without editing this file.
 */
const themes = [
  ['light', 'sorbet'],
  ['dark', 'night-garden'],
] as const;

async function storyIds(page: Page): Promise<string[]> {
  const response = await page.request.get('/meta.json');
  const meta = (await response.json()) as { stories: Record<string, unknown> };
  return Object.keys(meta.stories).sort();
}

test('every base component has at least one story', async ({ page }) => {
  const ids = await storyIds(page);
  const components = new Set(ids.map((id) => id.split('--').slice(0, -1).join('--')));
  expect([...components].sort()).toEqual(
    [
      'bottomnav',
      'button',
      'card',
      'chip',
      'codelist',
      'datetimepicker',
      'dialog',
      'emptystate',
      'errorstate',
      'fab',
      'icon',
      'installguide',
      'layout--grid',
      'layout--stack',
      'lockscreen',
      'notificationpermissioncard',
      'select',
      'sheet',
      'skeleton',
      'switch',
      'textarea',
      'textfield',
      'toast',
    ].sort(),
  );
});

for (const [theme, label] of themes) {
  test(`every story in ${label}`, async ({ page }) => {
    test.setTimeout(180_000);
    for (const story of await storyIds(page)) {
      await test.step(story, async () => {
        await page.goto(`/?story=${story}&mode=preview&theme=${theme}`);
        await expect(page.locator('[data-story-root]')).toBeAttached();
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        await page.evaluate(() => document.fonts.ready);
        const axe = await new AxeBuilder({ page }).analyze();
        expect.soft(axe.violations.map((v) => `${story}: ${v.id}: ${v.help}`)).toEqual([]);
        await expect.soft(page).toHaveScreenshot(`${story}--${label}.png`, { fullPage: true });
      });
    }
  });
}
