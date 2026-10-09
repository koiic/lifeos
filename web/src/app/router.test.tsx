import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../copy/en-GB';
import { REASON } from '../lib/auth/session';
import { refreshSubscription } from '../lib/push/push';
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
const signedIn = () => fakeApi({ [SESSIONS]: { body: { items: [], next_cursor: null } } });

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
    expect(await screen.findByRole('heading', { name: copy.today.title }, LAZY)).toBeDefined();
    expect(router.state.location.pathname).toBe('/today');
  });

  it('declares every screen route as lazy (code-split)', () => {
    for (const path of [
      'today',
      'register',
      'signin',
      'recover',
      'settings/security',
      'install',
      'setup/notifications',
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
    expect(await screen.findByRole('heading', { name: copy.today.title }, LAZY)).toBeDefined();
    expect(refreshSubscription).toHaveBeenCalledOnce();
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
