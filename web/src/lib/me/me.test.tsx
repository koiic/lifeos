import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api';
import { fakeApi } from '../testing/fakeApi';
import { meBody } from '../testing/me';
import { ME_KEY, useChangeProfile, useChangeSettings, useMe } from './me';

const ME = 'GET /api/v1/me';
const PROFILE = 'PATCH /api/v1/me';
const SETTINGS = 'PATCH /api/v1/me/settings';

afterEach(() => vi.unstubAllGlobals());

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, Wrapper };
}

describe('her profile and settings (GET /me, T09)', () => {
  it('loads /me once for the app', async () => {
    const api = fakeApi({ [ME]: { body: meBody() } });
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useMe(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.data?.profile.display_name).toBe('Zee'));
    expect(api.count(ME)).toBe(1);
  });
});

describe('[SET-1] [SET-2] saving changes with the version (CR-004)', () => {
  it('sends the version it read in If-Match and keeps the saved settings', async () => {
    const api = fakeApi({
      [ME]: { body: meBody() },
      [SETTINGS]: { body: { ...meBody().settings, theme: 'dark', version: 's2' } },
    });
    const { client, Wrapper } = wrapper();
    const { result } = renderHook(() => ({ me: useMe(), change: useChangeSettings() }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.me.isSuccess).toBe(true));
    await act(() => result.current.change.mutateAsync({ theme: 'dark' }));
    expect(api.bodies(SETTINGS)).toEqual([{ theme: 'dark' }]);
    expect(api.headers(SETTINGS)[0]?.get('If-Match')).toBe('"s1"');
    const cached = client.getQueryData<ReturnType<typeof meBody>>(ME_KEY);
    expect(cached?.settings).toMatchObject({ theme: 'dark', version: 's2' });
  });

  it('profile changes go to PATCH /me with the profile version', async () => {
    const api = fakeApi({
      [ME]: { body: meBody() },
      [PROFILE]: { body: { ...meBody().profile, timezone: 'Africa/Lagos', version: 'p2' } },
    });
    const { client, Wrapper } = wrapper();
    const { result } = renderHook(() => ({ me: useMe(), change: useChangeProfile() }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.me.isSuccess).toBe(true));
    await act(() => result.current.change.mutateAsync({ timezone: 'Africa/Lagos' }));
    expect(api.headers(PROFILE)[0]?.get('If-Match')).toBe('"p1"');
    const cached = client.getQueryData<ReturnType<typeof meBody>>(ME_KEY);
    expect(cached?.profile).toMatchObject({ timezone: 'Africa/Lagos', version: 'p2' });
  });

  it('a conflict (409) takes the current settings from the server and still fails', async () => {
    const current = { ...meBody().settings, theme: 'light', version: 's9' };
    fakeApi({
      [ME]: { body: meBody() },
      [SETTINGS]: {
        status: 409,
        body: { type: 'about:blank', title: 'Conflict', status: 409, detail: 'x', current },
        headers: { 'Content-Type': 'application/problem+json' },
      },
    });
    const { client, Wrapper } = wrapper();
    const { result } = renderHook(() => ({ me: useMe(), change: useChangeSettings() }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.me.isSuccess).toBe(true));
    const error = await result.current.change.mutateAsync({ theme: 'dark' }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    const cached = client.getQueryData<ReturnType<typeof meBody>>(ME_KEY);
    expect(cached?.settings).toMatchObject({ theme: 'light', version: 's9' });
  });
});
