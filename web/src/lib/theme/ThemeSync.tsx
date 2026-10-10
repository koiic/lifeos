// SET-2, spec 11.7: her saved theme (`GET /me`) is applied, and kept on this device so the next
// start opens in it before /me answers (a per-device convenience; the server holds the setting).
import { useEffect } from 'react';

import { useMe } from '../me/me';
import { applyTheme, type ThemeSetting } from './theme';

const KEY = 'lifeos.theme';
const SETTINGS: readonly ThemeSetting[] = ['system', 'light', 'dark'];

/** The theme this device last applied for her; `system` when there is none (or storage fails). */
export function savedTheme(): ThemeSetting {
  try {
    const value = localStorage.getItem(KEY);
    return SETTINGS.find((setting) => setting === value) ?? 'system';
  } catch {
    return 'system';
  }
}

export function rememberTheme(setting: ThemeSetting): void {
  try {
    localStorage.setItem(KEY, setting);
  } catch {
    // Private mode or blocked storage: the next start follows the system until /me answers.
  }
}

/** Applies her theme whenever it changes; renders nothing. */
export function ThemeSync() {
  const theme = useMe().data?.settings.theme;
  useEffect(() => {
    if (theme === undefined) return undefined;
    rememberTheme(theme);
    return applyTheme(theme);
  }, [theme]);
  return null;
}
