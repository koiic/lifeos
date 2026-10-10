import { cleanup, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_LOCK_TIMEOUT_S } from '../lib/lock/rules';
import { useLockStore } from '../lib/lock/store';
import { startLockWatch } from '../lib/lock/watch';
import { fakeApi } from '../lib/testing/fakeApi';
import { meBody } from '../lib/testing/me';
import { renderRoute } from '../lib/testing/renderRoute';
import { AppLock } from './AppLock';

vi.mock('../lib/lock/watch', () => ({ startLockWatch: vi.fn(() => () => undefined) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(startLockWatch).mockClear();
});

describe('[AUTH-6] the lock timeout is hers (CR-025, from GET /me)', () => {
  it('starts with the spec default, then watches with her saved timeout', async () => {
    useLockStore.setState({ locked: false, covered: false });
    fakeApi({ 'GET /api/v1/me': { body: meBody({ settings: { app_lock_timeout_s: 900 } }) } });
    renderRoute(
      <AppLock>
        <p>app</p>
      </AppLock>,
      { path: '/today', url: '/today' },
    );
    expect(vi.mocked(startLockWatch).mock.calls[0]?.[0]).toEqual({
      timeoutS: DEFAULT_LOCK_TIMEOUT_S,
    });
    await waitFor(() =>
      expect(vi.mocked(startLockWatch).mock.calls.at(-1)?.[0]).toEqual({ timeoutS: 900 }),
    );
  });
});
