import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { createMemoryRouter, Navigate, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../copy/en-GB';
import { expectNoAxeViolations } from '../ui/testing/axe';
import { AppShell } from './AppShell';

const t = copy.nav;

afterEach(cleanup);

function open(url: string) {
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { path: '/health', element: <Navigate to="/health/cycle" replace /> },
          ...['/today', '/health/cycle', '/health/history', '/calendar', '/more'].map((path) => ({
            path,
            element: <h1>{path}</h1>,
          })),
        ],
      },
    ],
    { initialEntries: [url] },
  );
  return { ...render(<RouterProvider router={router} />), router };
}

describe('the bottom bar (spec 5.1)', () => {
  it('has the five slots in order: Today, Health, +, Calendar, More', async () => {
    const { container } = open('/today');
    const nav = screen.getByRole('navigation', { name: t.label });
    const names = [...nav.querySelectorAll('a, button')].map(
      (control) => control.getAttribute('aria-label') ?? control.textContent,
    );
    expect(names).toEqual([t.today, t.health, t.add, t.calendar, t.more]);
    await expectNoAxeViolations(container);
  });

  it.each([
    [t.today, '/today'],
    [t.health, '/health/cycle'],
    [t.calendar, '/calendar'],
    [t.more, '/more'],
  ])('%s reaches its tab and is marked current', (name, path) => {
    const { router } = open('/today');
    fireEvent.click(screen.getByRole('link', { name }));
    expect(router.state.location.pathname).toBe(path);
    expect(screen.getByRole('heading', { name: path })).toBeDefined();
    expect(screen.getByRole('link', { name }).getAttribute('aria-current')).toBe('page');
  });

  it.each(['/health/cycle', '/health/history'])('Health stays current on %s', (path) => {
    open(path);
    expect(screen.getByRole('link', { name: t.health }).getAttribute('aria-current')).toBe('page');
  });

  it('"+" opens the quick-add sheet, and the bar is not shown under it', () => {
    open('/today');
    fireEvent.click(screen.getByRole('button', { name: t.add }));
    const sheet = screen.getByRole('dialog', { name: copy.quickAdd.title });
    expect(within(sheet).getByText(copy.quickAdd.empty)).toBeDefined();
    expect(screen.queryByRole('navigation', { name: t.label })).toBeNull();
    fireEvent.click(within(sheet).getByRole('button', { name: copy.quickAdd.close }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('navigation', { name: t.label })).toBeDefined();
  });
});
