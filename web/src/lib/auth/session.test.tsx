import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useLockStore } from '../lock/store';
import { fakeApi, problem } from '../testing/fakeApi';
import { REASON, signOut, useSession } from './session';

const SESSIONS = 'GET /api/v1/auth/sessions';

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('[AUTH-5] session state', () => {
  it('signed in when the session list loads', async () => {
    fakeApi({ [SESSIONS]: { body: { items: [], next_cursor: null } } });
    const { result } = renderHook(() => useSession(), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.status).toBe('signed-in'));
  });

  it('signed out on 401', async () => {
    fakeApi({ [SESSIONS]: problem(401, REASON.notSignedIn) });
    const { result } = renderHook(() => useSession(), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.status).toBe('signed-out'));
  });

  it('pending when the password account is not yet activated (CR-014)', async () => {
    fakeApi({ [SESSIONS]: problem(403, REASON.notActivated) });
    const { result } = renderHook(() => useSession(), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.status).toBe('pending'));
  });

  it('an unexpected failure is an error, not a sign-out', async () => {
    fakeApi({ [SESSIONS]: problem(500, 'boom') });
    const { result } = renderHook(() => useSession(), { wrapper: wrapper(client()) });
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('sign-out ends the session, clears cached data and the lock (spec 11.4)', async () => {
    const api = fakeApi({ 'POST /api/v1/auth/signout': {} });
    const queries = client();
    queries.setQueryData(['today', '2026-10-08'], { secret: 'cached' });
    useLockStore.setState({ locked: true, covered: true });
    await signOut(queries);
    expect(api.count('POST /api/v1/auth/signout')).toBe(1);
    expect(queries.getQueryData(['today', '2026-10-08'])).toBeUndefined();
    expect(useLockStore.getState()).toMatchObject({ locked: false, covered: false });
  });

  it('sign-out clears local data even when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    const queries = client();
    queries.setQueryData(['cycle'], { secret: 'cached' });
    await signOut(queries);
    expect(queries.getQueryData(['cycle'])).toBeUndefined();
  });
});
