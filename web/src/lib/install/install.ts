// ONB-1: is the app running installed (from the Home Screen), and which steps install it here.

/** `iosOtherBrowser`: Chrome, Firefox and others on iOS cannot add to the Home Screen like Safari. */
export type Platform = 'ios' | 'iosOtherBrowser' | 'android' | 'other';

/** Kept per browser when she chooses "not now" (spec ONB-1: dismissible). */
export const INSTALL_DISMISSED_KEY = 'lifeos.installDismissed';

/** Opened from the Home Screen: `display-mode: standalone`, or iOS Safari's own flag. */
export function isStandalone(): boolean {
  const standalone =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(display-mode: standalone)').matches;
  const ios = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return standalone || ios;
}

/**
 * iPhone and iPad (iPadOS reports a Mac user agent, but a Mac has no touch screen), Android, or
 * anything else (a desktop browser).
 */
export function detectPlatform(userAgent: string, maxTouchPoints: number): Platform {
  const ios =
    /iPhone|iPad|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && maxTouchPoints > 1);
  if (ios) return /CriOS|FxiOS|EdgiOS|OPiOS/.test(userAgent) ? 'iosOtherBrowser' : 'ios';
  if (/Android/.test(userAgent)) return 'android';
  return 'other';
}

export function currentPlatform(): Platform {
  return detectPlatform(navigator.userAgent, navigator.maxTouchPoints);
}

export function wasInstallDismissed(): boolean {
  try {
    return localStorage.getItem(INSTALL_DISMISSED_KEY) !== null;
  } catch {
    return false;
  }
}

export function dismissInstall(): void {
  try {
    localStorage.setItem(INSTALL_DISMISSED_KEY, '1');
  } catch {
    // Storage blocked (private browsing): the guide shows again next time, which is harmless.
  }
}

/** Show the guide: in a browser tab, unless she said "not now". */
export function needsInstallGuide(): boolean {
  return !isStandalone() && !wasInstallDismissed();
}
