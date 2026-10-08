import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../copy/en-GB';
import { REASON } from '../lib/auth/session';
import { fakeApi, problem } from '../lib/testing/fakeApi';
import { renderRoute } from '../lib/testing/renderRoute';
import { RequireSession } from './RequireSession';

const SESSIONS = 'GET /api/v1/auth/sessions';

function open(url = '/today?tab=1') {
  return renderRoute(
    <RequireSession>
      <p>signed-in content</p>
    </RequireSession>,
    { path: '/today', url },
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('[AUTH-5] signed-in routes', () => {
  it('shows the screen when signed in', async () => {
    fakeApi({ [SESSIONS]: { body: { items: [], next_cursor: null } } });
    open();
    expect(await screen.findByText('signed-in content')).toBeDefined();
  });

  it('signed out (or revoked elsewhere): her cached data is cleared (spec 11.4)', async () => {
    fakeApi({ [SESSIONS]: problem(401, REASON.notSignedIn) });
    const { queryClient } = open();
    queryClient.setQueryData(['today', '2026-10-08'], { secret: 'cached' });
    await screen.findByTestId('arrived');
    expect(queryClient.getQueryData(['today', '2026-10-08'])).toBeUndefined();
  });

  it('signed out: goes to sign-in and remembers where she was', async () => {
    fakeApi({ [SESSIONS]: problem(401, REASON.notSignedIn) });
    open();
    expect((await screen.findByTestId('arrived')).textContent).toBe(
      `/signin?next=${encodeURIComponent('/today?tab=1')}`,
    );
  });

  it('a password account not yet confirmed goes back to the code step (CR-014)', async () => {
    fakeApi({ [SESSIONS]: problem(403, REASON.notActivated) });
    open();
    expect((await screen.findByTestId('arrived')).textContent).toBe('/register?step=confirm');
  });

  it('shows loading while checking, and nothing of the screen', () => {
    fakeApi({ [SESSIONS]: { body: { items: [], next_cursor: null } } });
    open();
    expect(screen.getByRole('status', { name: copy.common.loading })).toBeDefined();
    expect(screen.queryByText('signed-in content')).toBeNull();
  });

  it('a server problem offers a retry instead of signing her out', async () => {
    fakeApi({
      [SESSIONS]: [problem(503, 'down'), { body: { items: [], next_cursor: null } }],
    });
    open();
    fireEvent.click(await screen.findByRole('button', { name: copy.common.retry }));
    expect(await screen.findByText('signed-in content')).toBeDefined();
  });
});
