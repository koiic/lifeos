import { expect, type Page, test } from '@playwright/test';

/**
 * Plan 5.3 rules 3 and 5, spec 5.6 and 5.8, checked in a real browser on every story:
 * - every control is at least 44 × 44 px;
 * - keyboard focus reaches every control and shows a 2 px solid ring with a 2 px offset, in the
 *   surrounding surface's text colour (CR-023, CR-024), the colour proven against that surface;
 * - with reduced motion nothing transitions or animates;
 * - the sheet and dialog scrim dims the page;
 * and the keyboard operates the choice chips and the switch.
 */

declare global {
  interface Window {
    /** Every element the story renders: inside the story root, or portalled into <body>. */
    storyElements: () => HTMLElement[];
  }
}

const CONTROLS = [
  'button',
  'a[href]',
  'select',
  'textarea',
  'input:not([type="radio"])',
  '[role="switch"]',
].join(', ');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.storyElements = () => {
      const roots = [
        ...document.querySelectorAll<HTMLElement>('[data-story-root]'),
        // Portals (Sheet, Dialog) are <body> children beside Ladle's own two.
        ...[...document.body.children].filter(
          (el): el is HTMLElement =>
            el instanceof HTMLElement &&
            el.id !== 'ladle-root' &&
            !el.classList.contains('ladle-background') &&
            el.tagName !== 'SCRIPT',
        ),
      ];
      return roots.flatMap((root) => [root, ...root.querySelectorAll<HTMLElement>('*')]);
    };
  });
});

async function storyIds(page: Page): Promise<string[]> {
  const response = await page.request.get('/meta.json');
  const meta = (await response.json()) as { stories: Record<string, unknown> };
  return Object.keys(meta.stories).sort();
}

async function open(page: Page, story: string, theme: 'light' | 'dark' = 'light') {
  await page.goto(`/?story=${story}&mode=preview&theme=${theme}`);
  await expect(page.locator('[data-story-root]')).toBeAttached();
  await page.evaluate(() => document.fonts.ready);
}

test('every control is at least 44 × 44 px (spec 5.8)', async ({ page }) => {
  test.setTimeout(120_000);
  for (const story of await storyIds(page)) {
    await test.step(story, async () => {
      await open(page, story);
      const small = await page.evaluate((selector) => {
        const targets = window
          .storyElements()
          .filter((el) => el.matches(selector))
          .concat(
            // A visually hidden radio is operated through its label.
            window
              .storyElements()
              .filter((el) => el.matches('input[type="radio"]'))
              .map((radio) => radio.closest('label') ?? radio),
          );
        return targets
          .map((el) => ({ el, box: el.getBoundingClientRect() }))
          .filter(({ box }) => box.width < 44 || box.height < 44)
          .map(({ el, box }) => `${el.tagName} "${el.textContent}" ${box.width}×${box.height}`);
      }, CONTROLS);
      expect.soft(small, story).toEqual([]);
    });
  }
});

for (const theme of ['light', 'dark'] as const) {
  test(`Tab reaches every control and shows the ring in the surface's text colour (spec 5.8, CR-024) — ${theme}`, async ({
    page,
  }) => {
    test.setTimeout(180_000);
    for (const story of await storyIds(page)) {
      await test.step(story, async () => {
        await open(page, story, theme);
        // Tab stops: one per control, one per radio group (the checked radio).
        const expected = await page.evaluate(() => {
          const elements = window.storyElements();
          const controls = elements.filter(
            (el) =>
              el.matches(
                'button:not([disabled]), a[href], select:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type="radio"])',
              ) && el.closest('[inert]') === null,
          );
          const groups = new Set(
            elements
              .filter((el): el is HTMLInputElement => el.matches('input[type="radio"]'))
              .map((radio) => radio.name),
          );
          return controls.length + groups.size;
        });
        let visited = 0;
        for (let i = 0; i < expected * 4 + 5; i += 1) {
          await page.keyboard.press('Tab');
          const ring = await page.evaluate(() => {
            const active = document.activeElement;
            if (!(active instanceof HTMLElement) || !window.storyElements().includes(active)) {
              return null;
            }
            // A date/time input keeps focus while Tab walks its day, month and year parts.
            if (active.dataset.current === 'true') return 'same';
            for (const el of document.querySelectorAll<HTMLElement>('[data-current]')) {
              delete el.dataset.current;
            }
            active.dataset.current = 'true';
            if (active.dataset.visited === 'true') return 'repeat';
            active.dataset.visited = 'true';
            // A hidden radio's ring is drawn on the chip next to it.
            const shown =
              active instanceof HTMLInputElement && active.type === 'radio'
                ? (active.nextElementSibling as HTMLElement)
                : active;
            const style = getComputedStyle(shown);
            const around = getComputedStyle(shown.parentElement ?? document.body).color;
            return {
              text: `${active.tagName} "${active.getAttribute('aria-label') ?? active.textContent}"`,
              outline: `${style.outlineStyle} ${style.outlineWidth} offset ${style.outlineOffset}`,
              matches: style.outlineColor === around,
            };
          });
          if (ring === 'repeat') break;
          if (ring === null || ring === 'same') continue; // browser UI between laps; date parts
          visited += 1;
          expect.soft(ring.outline, `${story}: ${ring.text}`).toBe('solid 2px offset 2px');
          expect.soft(ring.matches, `${story}: ${ring.text} ring colour`).toBe(true);
        }
        expect.soft(visited, `${story}: controls reached by Tab`).toBe(expected);
      });
    }
  });
}

test('nothing moves under prefers-reduced-motion (spec 5.6)', async ({ page }) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const story of await storyIds(page)) {
    await test.step(story, async () => {
      await open(page, story);
      const moving = await page.evaluate(() => {
        const moves = (style: CSSStyleDeclaration) =>
          style.transitionDuration.split(',').some((d) => parseFloat(d) > 0) ||
          (style.animationName !== 'none' &&
            style.animationDuration.split(',').some((d) => parseFloat(d) > 0));
        return window
          .storyElements()
          .flatMap((el) =>
            [null, '::before', '::after']
              .filter((pseudo) => moves(getComputedStyle(el, pseudo)))
              .map((pseudo) => `${el.tagName}.${el.className}${pseudo ?? ''}`),
          );
      });
      expect.soft(moving, story).toEqual([]);
    });
  }
});

for (const theme of ['light', 'dark'] as const) {
  test(`the sheet and dialog scrim dims the page (CR-023) — ${theme}`, async ({ page }) => {
    for (const story of ['sheet--open', 'dialog--confirmation', 'dialog--plain']) {
      await test.step(story, async () => {
        await open(page, story, theme);
        const result = await page.evaluate(() => {
          const luminance = (colour: string) => {
            const [r, g, b] = (colour.match(/\d+(\.\d+)?/g) ?? []).slice(0, 3).map(Number);
            const lin = (c = 0) => {
              const s = c / 255;
              return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
            };
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
          };
          const scrim = document.querySelector<HTMLElement>('[data-scrim]');
          if (scrim === null) return null;
          const style = getComputedStyle(scrim);
          return {
            scrim: luminance(style.backgroundColor),
            opacity: Number(style.opacity),
            page: luminance(getComputedStyle(document.documentElement).backgroundColor),
          };
        });
        expect(result, `${story}: scrim element`).not.toBeNull();
        expect(result?.scrim ?? 1, `${story}: scrim darker than the page`).toBeLessThan(
          result?.page ?? 0,
        );
        expect(result?.opacity ?? 0, `${story}: scrim is visible`).toBeGreaterThan(0);
      });
    }
  });
}

test('arrow keys move the choice chip selection', async ({ page }) => {
  await open(page, 'chip--choice');
  const medium = page.getByRole('radio', { name: 'Medium' });
  await medium.focus();
  await expect(medium).toBeChecked();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('radio', { name: 'Heavy' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'Heavy' })).toBeFocused();
  await expect(medium).not.toBeChecked();
});

test('Space and Enter toggle the switch', async ({ page }) => {
  await open(page, 'switch--states');
  const control = page.getByRole('switch').first();
  const before = await control.getAttribute('aria-checked');
  expect(['true', 'false']).toContain(before);
  const after = before === 'true' ? 'false' : 'true';
  await control.focus();
  await page.keyboard.press('Space');
  await expect(control).toHaveAttribute('aria-checked', after);
  await page.keyboard.press('Enter');
  await expect(control).toHaveAttribute('aria-checked', before ?? '');
});

test('a mouse click on the Sheet close button closes it (CR-024: the non-drag way)', async ({
  page,
}) => {
  await open(page, 'sheet--open');
  await page.getByRole('button', { name: 'Close' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('a busy submit button submits neither on click nor on Enter', async ({ page }) => {
  await open(page, 'button--busy-submit');
  await page.getByRole('button', { name: 'Saving' }).click({ force: true });
  await page.getByLabel('Note').press('Enter');
  await expect(page.locator('[data-submits]')).toHaveAttribute('data-submits', '0');
});
