import { cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../copy/en-GB';
import { routes } from './router';

afterEach(cleanup);

describe('router', () => {
  it('redirects / to /today and loads the Today route lazily', async () => {
    const router = createMemoryRouter(routes, { initialEntries: ['/'] });
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole('heading', { name: copy.today.title })).toBeDefined();
    expect(router.state.location.pathname).toBe('/today');
  });

  it('declares the Today route as lazy (code-split)', () => {
    const root = routes[0];
    const today = root?.children?.find((route) => route.path === 'today');
    expect(today?.lazy).toBeTypeOf('function');
  });

  it('shows the error boundary for unknown routes', async () => {
    const router = createMemoryRouter(routes, { initialEntries: ['/no-such-page'] });
    render(<RouterProvider router={router} />);
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
