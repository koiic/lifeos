// Her profile and settings (spec 9.2 `GET /me`, `PATCH /me`, `PATCH /me/settings`; T09). A change
// sends the version it read in `If-Match`; a conflict (409) brings the current one (CR-004).
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { api, ApiError, type components } from '../api';

export type Me = components['schemas']['Me'];
export type Profile = components['schemas']['Profile'];
export type Settings = components['schemas']['Settings'];
export type ProfileChange = components['schemas']['ProfileChange'];
export type SettingsChange = components['schemas']['SettingsChange'];

export const ME_KEY = ['me'] as const;

export const meQuery = {
  queryKey: ME_KEY,
  queryFn: () => api.request('GET', '/api/v1/me'),
};

export function useMe() {
  return useQuery(meQuery);
}

function ifMatch(version: string | undefined): Record<string, string> {
  return version === undefined ? {} : { 'If-Match': `"${version}"` };
}

function update(client: QueryClient, part: Partial<Pick<Me, 'profile' | 'settings'>>): void {
  client.setQueryData<Me>(ME_KEY, (me) => {
    if (me === undefined) return me;
    const next = { ...me, ...part };
    // CR-030: whether the device's timezone is hers follows her (new) profile timezone.
    const zone = next.device_timezone;
    return { ...next, timezone_differs: zone !== null && zone !== next.profile.timezone };
  });
}

/** On a conflict, the server's current resource replaces the stale one; the error stands. */
function current<T>(error: unknown): T | undefined {
  return error instanceof ApiError && error.status === 409
    ? (error.body['current'] as T | undefined)
    : undefined;
}

export function useChangeProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (change: ProfileChange) =>
      api.request(
        'PATCH',
        '/api/v1/me',
        change,
        {},
        ifMatch(client.getQueryData<Me>(ME_KEY)?.profile.version),
      ),
    onSuccess: (profile) => update(client, { profile }),
    onError: (error) => {
      const profile = current<Profile>(error);
      if (profile !== undefined) update(client, { profile });
    },
  });
}

export function useChangeSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (change: SettingsChange) =>
      api.request(
        'PATCH',
        '/api/v1/me/settings',
        change,
        {},
        ifMatch(client.getQueryData<Me>(ME_KEY)?.settings.version),
      ),
    onSuccess: (settings) => update(client, { settings }),
    onError: (error) => {
      const settings = current<Settings>(error);
      if (settings !== undefined) update(client, { settings });
    },
  });
}

/**
 * CR-030 (SET-1 "auto-detected"): right after registering, her profile takes the device's
 * timezone when they differ. Quiet on failure: Today offers the switch later.
 */
export async function adoptDeviceTimezone(client: QueryClient): Promise<void> {
  try {
    const me = await client.fetchQuery({
      queryKey: ME_KEY,
      queryFn: () => api.request('GET', '/api/v1/me'),
    });
    if (!me.timezone_differs || me.device_timezone === null) return;
    const profile = await api.request(
      'PATCH',
      '/api/v1/me',
      { timezone: me.device_timezone },
      {},
      ifMatch(me.profile.version),
    );
    update(client, { profile });
  } catch {
    // Offline or refused: nothing is lost; the prompt on Today covers it.
  }
}
