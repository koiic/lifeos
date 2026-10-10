import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fakeApi } from '../testing/fakeApi';
import { meBody } from '../testing/me';
import { savedTheme, ThemeSync } from './ThemeSync';

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

describe('[SET-2] her saved theme is applied (spec 11.7)', () => {
  it('applies the theme from /me and keeps it on the device for the next start', async () => {
    fakeApi({ 'GET /api/v1/me': { body: meBody({ settings: { theme: 'dark' } }) } });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ThemeSync />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    expect(savedTheme()).toBe('dark');
  });

  it('the device remembers nothing usable: system', () => {
    expect(savedTheme()).toBe('system');
    localStorage.setItem('lifeos.theme', 'sepia');
    expect(savedTheme()).toBe('system');
  });
});
