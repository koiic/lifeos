import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { applyTheme, resolveTheme } from './theme';

/** Stands in for the stylesheet's --bg, so most tests need no CSS; the last test reads the real one. */
const readBackground = () =>
  document.documentElement.dataset.theme === 'dark' ? 'night-bg' : 'sorbet-bg';

type Listener = (event: { matches: boolean }) => void;

/** A controllable prefers-color-scheme media query. */
function fakeColorScheme(dark: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: dark,
    media: '(prefers-color-scheme: dark)',
    addEventListener: (_: string, fn: Listener) => listeners.add(fn),
    removeEventListener: (_: string, fn: Listener) => listeners.delete(fn),
  };
  window.matchMedia = ((media: string) => {
    if (media !== query.media) throw new Error(`unexpected media query ${media}`);
    return query;
  }) as unknown as typeof window.matchMedia;
  return {
    change(next: boolean) {
      query.matches = next;
      for (const fn of listeners) fn({ matches: next });
    },
    listenerCount: () => listeners.size,
  };
}

function themeColorMeta(): HTMLMetaElement | null {
  return document.head.querySelector('meta[name="theme-color"]');
}

describe('theme (spec 5.3: data-theme on <html>; 11.7: theme-color follows the theme)', () => {
  let stop: () => void = () => undefined;

  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme');
    themeColorMeta()?.remove();
  });
  afterEach(() => stop());

  it('resolves system from prefers-color-scheme', () => {
    fakeColorScheme(true);
    expect(resolveTheme('system')).toBe('dark');
    fakeColorScheme(false);
    expect(resolveTheme('system')).toBe('light');
    expect(resolveTheme('dark')).toBe('dark');
    expect(resolveTheme('light')).toBe('light');
  });

  it('an override sets data-theme and the theme-color meta', () => {
    fakeColorScheme(false);
    stop = applyTheme('dark', readBackground);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(themeColorMeta()?.content).toBe('night-bg');
    stop();
    stop = applyTheme('light', readBackground);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(themeColorMeta()?.content).toBe('sorbet-bg');
  });

  it('system follows the OS setting as it changes, until stopped', () => {
    const scheme = fakeColorScheme(false);
    stop = applyTheme('system', readBackground);
    expect(document.documentElement.dataset.theme).toBe('light');
    scheme.change(true);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(themeColorMeta()?.content).toBe('night-bg');
    stop();
    expect(scheme.listenerCount()).toBe(0);
    scheme.change(false);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('an override ignores the OS setting', () => {
    const scheme = fakeColorScheme(false);
    stop = applyTheme('dark', readBackground);
    scheme.change(false);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(scheme.listenerCount()).toBe(0);
  });

  it('reuses one theme-color meta element', () => {
    fakeColorScheme(false);
    applyTheme('light', readBackground)();
    stop = applyTheme('dark', readBackground);
    expect(document.head.querySelectorAll('meta[name="theme-color"]')).toHaveLength(1);
  });

  it("by default reads theme-color from the applied theme's --bg in the stylesheet", () => {
    fakeColorScheme(false);
    const style = document.createElement('style');
    style.textContent = ":root { --bg: sorbet-bg; } :root[data-theme='dark'] { --bg: night-bg; }";
    document.head.append(style);
    try {
      applyTheme('dark');
      expect(themeColorMeta()?.content).toBe('night-bg');
      applyTheme('light');
      expect(themeColorMeta()?.content).toBe('sorbet-bg');
    } finally {
      style.remove();
    }
  });
});
