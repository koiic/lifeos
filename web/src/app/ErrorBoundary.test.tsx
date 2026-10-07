import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../copy/en-GB';
import * as api from '../lib/api';
import { reportedRoute, RouteErrorBoundary } from './ErrorBoundary';
import { routes } from './router';

function Thrower(): never {
  throw new Error('failed while reading the note "private"');
}

function renderAt(routeTable: RouteObject[], path: string) {
  const router = createMemoryRouter(routeTable, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

const failingRoute: RouteObject[] = [
  {
    path: '/health/:tab',
    element: <Thrower />,
    errorElement: <RouteErrorBoundary />,
    handle: { pattern: '/health/:tab' },
  },
];

// React 18 re-dispatches render errors as window "error" events in development; jsdom would print
// the deliberately thrown test error. preventDefault() keeps the test output readable.
function silenceExpectedError(event: ErrorEvent) {
  event.preventDefault();
}

beforeEach(() => {
  vi.spyOn(api, 'reportClientError').mockResolvedValue(undefined);
  // React logs caught render errors; expected here and asserted on below.
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  window.addEventListener('error', silenceExpectedError);
});

afterEach(() => {
  window.removeEventListener('error', silenceExpectedError);
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('RouteErrorBoundary', () => {
  it('shows the copy and a Reload button, never the error or stack', () => {
    renderAt(failingRoute, '/health/cycle');
    expect(screen.getByRole('heading', { name: copy.errors.title })).toBeDefined();
    expect(screen.getByRole('button', { name: copy.errors.reload })).toBeDefined();
    expect(document.body.textContent).not.toContain('private');
    expect(document.body.textContent).not.toContain('at ');
  });

  it('reports the declared route pattern, not the raw path', () => {
    renderAt(failingRoute, '/health/2026-10-06');
    expect(api.reportClientError).toHaveBeenCalledOnce();
    const [error, route] = vi.mocked(api.reportClientError).mock.calls[0] ?? [];
    expect(error).toBeInstanceOf(Error);
    expect(route).toBe('/health/:tab');
  });

  it('survives malformed percent-encoding in the URL', () => {
    renderAt(failingRoute, '/health/100%');
    expect(screen.getByRole('heading', { name: copy.errors.title })).toBeDefined();
    expect(vi.mocked(api.reportClientError).mock.calls[0]?.[1]).toBe('/health/:tab');
  });

  it('reports errors from child routes of the real route table with their pattern', async () => {
    const [root] = routes;
    if (!root) throw new Error('no root route');
    // The real root (layout, error boundary, handle) with one extra child that throws.
    const withThrowingChild = {
      ...root,
      children: [
        ...(root.children ?? []),
        { path: 'boom/:id', handle: { pattern: '/boom/:id' }, element: <Thrower /> },
      ],
    } as RouteObject;
    const table: RouteObject[] = [withThrowingChild];
    renderAt(table, '/boom/0192f2a1');
    await waitFor(() => {
      expect(api.reportClientError).toHaveBeenCalledOnce();
    });
    expect(vi.mocked(api.reportClientError).mock.calls[0]?.[1]).toBe('/boom/:id');
  });

  it('does not report unknown routes', async () => {
    renderAt(routes, '/no-such-page');
    expect(await screen.findByRole('heading', { name: copy.errors.title })).toBeDefined();
    expect(api.reportClientError).not.toHaveBeenCalled();
  });

  it('reloads the page when Reload is pressed', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    renderAt(failingRoute, '/health/cycle');
    fireEvent.click(screen.getByRole('button', { name: copy.errors.reload }));
    expect(reload).toHaveBeenCalledOnce();
  });
});

describe('reportedRoute', () => {
  it('uses the deepest declared pattern', () => {
    expect(reportedRoute([{ pattern: '/' }, undefined, { pattern: '/health/:tab' }])).toBe(
      '/health/:tab',
    );
  });

  it('falls back to "/" when no route declares one', () => {
    expect(reportedRoute([undefined, { other: 1 }])).toBe('/');
  });
});
