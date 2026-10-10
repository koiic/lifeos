import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { fakeApi, problem } from '../../lib/testing/fakeApi';
import { meBody } from '../../lib/testing/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { ThemeScreen } from './ThemeScreen';

const t = copy.theme;
const ME = 'GET /api/v1/me';
const SETTINGS = 'PATCH /api/v1/me/settings';

function open() {
  return renderRoute(<ThemeScreen />, { path: '/settings/theme', url: '/settings/theme' });
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  window.matchMedia = ((media: string) => ({
    matches: false,
    media,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('[SET-2] theme: Light (Sorbet), Dark (Night Garden), System (default)', () => {
  it('shows the three choices with hers selected', async () => {
    fakeApi({ [ME]: { body: meBody() } });
    const { container } = open();
    const system = await screen.findByRole('radio', { name: t.system });
    expect((system as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole('radio', { name: t.light })).toBeDefined();
    expect(screen.getByRole('radio', { name: t.dark })).toBeDefined();
    await expectNoAxeViolations(container);
  });

  it('choosing Dark applies it at once and saves it', async () => {
    const api = fakeApi({
      [ME]: { body: meBody() },
      [SETTINGS]: { body: { ...meBody().settings, theme: 'dark', version: 's2' } },
    });
    open();
    fireEvent.click(await screen.findByRole('radio', { name: t.dark }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await waitFor(() => expect(api.bodies(SETTINGS)).toEqual([{ theme: 'dark' }]));
    expect(localStorage.getItem('lifeos.theme')).toBe('dark');
  });

  it('if saving fails, her previous theme comes back and she is told', async () => {
    fakeApi({ [ME]: { body: meBody() }, [SETTINGS]: problem(503, 'down') });
    open();
    fireEvent.click(await screen.findByRole('radio', { name: t.dark }));
    expect(await screen.findByText(t.failed)).toBeDefined();
    expect((screen.getByRole('radio', { name: t.system }) as HTMLInputElement).checked).toBe(true);
    expect(document.documentElement.dataset.theme).toBe('light'); // system, the OS is light
  });
});
