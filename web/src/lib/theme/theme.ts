/**
 * Applies the theme (spec 5.3: `data-theme` on <html>; 11.7: `system` follows
 * `prefers-color-scheme`, and the theme sets `theme-color`). The theme-color value is the page
 * background token `--bg` of the applied theme, read from the stylesheet, so no colour is defined
 * here (plan 5.1).
 */

export type ThemeSetting = 'system' | 'light' | 'dark';
export type Theme = 'light' | 'dark';

const DARK_QUERY = '(prefers-color-scheme: dark)';

/** The applied theme's page background (`--bg`). */
export type BackgroundReader = () => string;

const readBackgroundToken: BackgroundReader = () =>
  getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();

export function resolveTheme(setting: ThemeSetting): Theme {
  if (setting !== 'system') return setting;
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

function themeColorMeta(): HTMLMetaElement {
  let meta = document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta === null) {
    meta = document.createElement('meta');
    meta.name = 'theme-color';
    document.head.append(meta);
  }
  return meta;
}

function set(theme: Theme, readBackground: BackgroundReader): void {
  document.documentElement.dataset.theme = theme;
  themeColorMeta().content = readBackground();
}

/**
 * Apply `setting` now; with `system`, keep following the OS until the returned function is called.
 */
export function applyTheme(
  setting: ThemeSetting,
  readBackground: BackgroundReader = readBackgroundToken,
): () => void {
  set(resolveTheme(setting), readBackground);
  if (setting !== 'system') return () => undefined;
  const query = window.matchMedia(DARK_QUERY);
  const follow = (event: { matches: boolean }) => {
    set(event.matches ? 'dark' : 'light', readBackground);
  };
  query.addEventListener('change', follow);
  return () => query.removeEventListener('change', follow);
}
