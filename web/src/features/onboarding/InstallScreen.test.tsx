import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { INSTALL_DISMISSED_KEY } from '../../lib/install/install';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { InstallScreen } from './InstallScreen';

const t = copy.install;

function device(userAgent: string, touchPoints: number, standalone = false) {
  vi.stubGlobal('navigator', { ...navigator, userAgent, maxTouchPoints: touchPoints });
  window.matchMedia = ((query: string) => ({
    matches: query === '(display-mode: standalone)' && standalone,
    media: query,
  })) as unknown as typeof window.matchMedia;
}

function open() {
  return renderRoute(<InstallScreen />, { path: '/install', url: '/install' });
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe('[ONB-1] install guide (/install)', () => {
  it('on an iPhone in Safari: the three iOS steps (Share → Add to Home Screen)', async () => {
    device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', 0);
    const { container } = open();
    expect(screen.getByRole('heading', { name: t.title })).toBeDefined();
    const steps = screen.getAllByRole('listitem').map((item) => item.textContent);
    expect(steps).toEqual([...t.steps.ios]);
    expect(screen.getByText(t.note)).toBeDefined();
    await expectNoAxeViolations(container);
  });

  it('on Android: the Chrome steps', () => {
    device('Mozilla/5.0 (Linux; Android 14; Pixel 7) Chrome/129.0 Mobile', 5);
    open();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      ...t.steps.android,
    ]);
  });

  it('elsewhere: the desktop browser steps', () => {
    device('Mozilla/5.0 (X11; Linux x86_64) Chrome/129.0', 0);
    open();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      ...t.steps.other,
    ]);
  });

  it('already installed (opened from the Home Screen): goes straight to Today', async () => {
    device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', 0, true);
    open();
    expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
  });

  it('dismissible: "not now" goes to Today and is remembered', async () => {
    device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', 0);
    open();
    fireEvent.click(screen.getByRole('button', { name: t.continue }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
    expect(localStorage.getItem(INSTALL_DISMISSED_KEY)).not.toBeNull();
  });

  it('arriving here moves focus to the heading (WCAG 2.4.3: the previous button is gone)', () => {
    device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', 0);
    open();
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: t.title }));
  });

  it('Chrome or Firefox on an iPhone: first open the page in Safari', () => {
    device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) CriOS/129.0 Mobile', 0);
    open();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      ...t.steps.iosOtherBrowser,
    ]);
  });

  it.each([
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)', ['share', 'addToHome', 'home']],
    [
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) CriOS/129.0',
      ['info', 'share', 'home'],
    ],
    ['Mozilla/5.0 (Linux; Android 14; Pixel 7) Chrome/129.0 Mobile', ['menu', 'addToHome', 'home']],
    ['Mozilla/5.0 (X11; Linux x86_64) Chrome/129.0', ['menu', 'addToHome', 'home']],
  ] as const)('each step has its own illustration (%s)', (agent, icons) => {
    device(agent, 0);
    open();
    const shown = screen
      .getAllByRole('listitem')
      .map((item) => item.querySelector('svg')?.getAttribute('data-icon'));
    expect(shown).toEqual([...icons]);
  });
});
