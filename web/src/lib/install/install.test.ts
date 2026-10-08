import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  detectPlatform,
  dismissInstall,
  INSTALL_DISMISSED_KEY,
  isStandalone,
  needsInstallGuide,
} from './install';

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';
const IPAD_DESKTOP_MODE =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15';
const ANDROID =
  'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36';
const DESKTOP =
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36';

function displayMode(standalone: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query === '(display-mode: standalone)' && standalone,
    media: query,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'standalone');
});

describe('[ONB-1] installed or not (display-mode: standalone)', () => {
  it('opened from the Home Screen: standalone', () => {
    displayMode(true);
    expect(isStandalone()).toBe(true);
  });

  it('in a browser tab: not standalone', () => {
    displayMode(false);
    expect(isStandalone()).toBe(false);
  });

  it("iOS's own flag also counts (navigator.standalone)", () => {
    displayMode(false);
    Object.defineProperty(navigator, 'standalone', { configurable: true, value: true });
    expect(isStandalone()).toBe(true);
  });
});

describe('[ONB-1] platform-specific steps', () => {
  it.each([
    [IPHONE, 0, 'ios'],
    [IPAD_DESKTOP_MODE, 5, 'ios'],
    [IPAD_DESKTOP_MODE, 0, 'other'],
    [ANDROID, 5, 'android'],
    [DESKTOP, 0, 'other'],
    [`${IPHONE.replace('Safari/604.1', 'CriOS/129.0 Safari/604.1')}`, 0, 'iosOtherBrowser'],
    [`${IPHONE.replace('Safari/604.1', 'FxiOS/131.0 Safari/604.1')}`, 0, 'iosOtherBrowser'],
    [`${IPHONE.replace('Safari/604.1', 'EdgiOS/129.0 Safari/604.1')}`, 0, 'iosOtherBrowser'],
    [`${IPHONE.replace('Safari/604.1', 'OPiOS/5.0 Safari/604.1')}`, 0, 'iosOtherBrowser'],
  ] as const)('%#: %s → %s', (agent, touchPoints, platform) => {
    expect(detectPlatform(agent, touchPoints)).toBe(platform);
  });
});

describe('[ONB-1] dismissible', () => {
  it('the guide is needed in a tab until she dismisses it', () => {
    displayMode(false);
    expect(needsInstallGuide()).toBe(true);
    dismissInstall();
    expect(localStorage.getItem(INSTALL_DISMISSED_KEY)).not.toBeNull();
    expect(needsInstallGuide()).toBe(false);
  });

  it('never needed once installed', () => {
    displayMode(true);
    expect(needsInstallGuide()).toBe(false);
  });

  it('works when storage is blocked', () => {
    displayMode(false);
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };
    try {
      expect(() => dismissInstall()).not.toThrow();
    } finally {
      Storage.prototype.setItem = original;
    }
  });

  it('if storage cannot be read, the guide is offered (never wrongly hidden)', () => {
    displayMode(false);
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error('blocked');
    };
    try {
      expect(needsInstallGuide()).toBe(true);
    } finally {
      Storage.prototype.getItem = original;
    }
  });
});
