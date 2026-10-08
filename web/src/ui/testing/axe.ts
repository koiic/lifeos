import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Plan 5.3 rule 3: zero axe violations. Colour contrast is not computed in jsdom (no layout); it is
 * checked by scripts/check_contrast.py on the tokens and by axe in Playwright on every story.
 */
export async function expectNoAxeViolations(container: Element): Promise<void> {
  const results = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false } },
  });
  const summary = results.violations.map((v) => `${v.id}: ${v.help}`);
  expect(summary).toEqual([]);
}
