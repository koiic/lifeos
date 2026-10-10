import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../copy/en-GB';
import { REASON } from '../lib/auth/session';
import { refreshSubscription } from '../lib/push/push';
import { meBody } from '../lib/testing/me';
import { fakeApi, problem } from '../lib/testing/fakeApi';
import { routes } from './router';

vi.mock('../lib/push/push', async (original) => ({
  ...(await original<typeof import('../lib/push/push')>()),
  refreshSubscription: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(refreshSubscription).mockClear();
});

const SESSIONS = 'GET /api/v1/auth/sessions';
// Lazy routes import their screen chunk first; under coverage instrumentation that takes longer
// than Testing Library's default 1 s wait.
const LAZY = { timeout: 5_000 };
const signedIn = () =>
  fakeApi({
    [SESSIONS]: { body: { items: [], next_cursor: null } },
    'GET /api/v1/me': { body: meBody() },
  });

function renderAt(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

function child(path: string) {
  const walk = (list: typeof routes): (typeof routes)[number] | undefined => {
    for (const route of list) {
      if (route.path === path) return route;
      const found = walk(route.children ?? []);
      if (found) return found;
    }
    return undefined;
  };
  return walk(routes);
}

describe('router', () => {
  it('redirects / to /today and loads the Today route lazily when signed in', async () => {
    signedIn();
    const router = renderAt('/');
    // The first route test transforms the shell and Today chunks while other files run.
    expect(await screen.findByRole('heading', { level: 1 }, { timeout: 25_000 })).toBeDefined();
    expect(router.state.location.pathname).toBe('/today');
  }, 30_000);

  it('declares every screen route as lazy (code-split)', () => {
    for (const path of [
      'today',
      'checkin',
      'register',
      'signin',
      'recover',
      'settings/security',
      'install',
      'setup/notifications',
      'health/cycle',
      'calendar',
      'more',
      'settings',
      'settings/profile',
      'settings/theme',
    ]) {
      expect(child(path)?.lazy, path).toBeTypeOf('function');
    }
  });

  it('[AUTH-5] signed-in screens send a signed-out visitor to sign-in', async () => {
    fakeApi({ [SESSIONS]: problem(401, REASON.notSignedIn) });
    // Today: a light signed-in route (the screen chunk is small), so this tests the wiring.
    const router = renderAt('/today?from=link');
    await waitFor(() => expect(router.state.location.pathname).toBe('/signin'), LAZY);
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent('/today?from=link')}`);
  });

  it('[ONB-3] the signed-in app re-registers its push subscription on start (spec 10.5)', async () => {
    signedIn();
    renderAt('/today');
    expect(await screen.findByRole('heading', { level: 1 }, LAZY)).toBeDefined();
    expect(refreshSubscription).toHaveBeenCalledOnce();
  });

  it('signed-in tabs sit in the shell with the bottom bar; setup does not (spec 5.1)', async () => {
    signedIn();
    renderAt('/settings');
    expect(
      await screen.findByRole('heading', { name: copy.settingsHome.title }, LAZY),
    ).toBeDefined();
    expect(screen.getByRole('navigation', { name: copy.nav.label })).toBeDefined();
    cleanup();
    signedIn();
    renderAt('/setup/notifications');
    expect(
      await screen.findByRole('heading', { name: copy.notifications.title }, LAZY),
    ).toBeDefined();
    expect(screen.queryByRole('navigation', { name: copy.nav.label })).toBeNull();
  });

  it('/health opens the Health hub at Cycle', async () => {
    signedIn();
    const router = renderAt('/health');
    await waitFor(() => expect(router.state.location.pathname).toBe('/health/cycle'), LAZY);
    expect(await screen.findByRole('heading', { name: copy.health.title }, LAZY)).toBeDefined();
  });

  it('the sign-in screen is open to a signed-out visitor', async () => {
    fakeApi({});
    renderAt('/signin');
    expect(
      await screen.findByRole('heading', { name: copy.auth.signIn.title }, LAZY),
    ).toBeDefined();
    expect(refreshSubscription).not.toHaveBeenCalled(); // signed out: nothing to re-register
  });

  it('shows the error boundary for unknown routes', async () => {
    renderAt('/no-such-page');
    expect(await screen.findByRole('heading', { name: copy.errors.title })).toBeDefined();
  });
});

describe('route handles', () => {
  it('declare the full path pattern on every route except index redirects', () => {
    const missing: string[] = [];
    const walk = (list: typeof routes, parent: string) => {
      for (const route of list) {
        if (route.index) continue;
        const path = route.path?.startsWith('/')
          ? route.path
          : `${parent === '/' ? '' : parent}/${route.path ?? ''}`;
        const pattern = (route.handle as { pattern?: unknown } | undefined)?.pattern;
        if (pattern !== path) missing.push(`${path} (handle: ${String(pattern)})`);
        walk(route.children ?? [], path);
      }
    };
    walk(routes, '');
    expect(missing).toEqual([]);
  });
});
