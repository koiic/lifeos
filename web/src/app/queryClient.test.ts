import { describe, expect, it } from 'vitest';

import { ApiError } from '../lib/api';
import { SESSION_KEY } from '../lib/auth/session';

import { createQueryClient, STALE_TIME } from './queryClient';

describe('query client (spec 11.4)', () => {
  it('uses 5 minutes for lists by default and refetches on focus and reconnect', () => {
    const queries = createQueryClient().getDefaultOptions().queries;
    expect(queries?.staleTime).toBe(5 * 60 * 1000);
    expect(queries?.refetchOnWindowFocus).toBe(true);
    expect(queries?.refetchOnReconnect).toBe(true);
  });

  it('defines 30 seconds for Today and cycle queries', () => {
    expect(STALE_TIME.today).toBe(30 * 1000);
    expect(STALE_TIME.cycle).toBe(30 * 1000);
    expect(STALE_TIME.list).toBe(5 * 60 * 1000);
  });

  it('[AUTH-5] any 401 (e.g. a session revoked elsewhere) re-checks the session', async () => {
    const client = createQueryClient();
    client.setQueryData(SESSION_KEY, 'signed-in');
    await client
      .fetchQuery({
        queryKey: ['today', '2026-10-08'],
        queryFn: () => Promise.reject(new ApiError(401, 'Unauthorized', 'Sign in to continue.')),
        retry: false,
      })
      .catch(() => undefined);
    expect(client.getQueryState(SESSION_KEY)?.isInvalidated).toBe(true);
  });

  it('other errors leave the session alone', async () => {
    const client = createQueryClient();
    client.setQueryData(SESSION_KEY, 'signed-in');
    await client
      .fetchQuery({
        queryKey: ['today', '2026-10-08'],
        queryFn: () => Promise.reject(new ApiError(500, 'Server Error', '')),
        retry: false,
      })
      .catch(() => undefined);
    expect(client.getQueryState(SESSION_KEY)?.isInvalidated).toBe(false);
  });

  it('[AUTH-5] a 401 from a mutation re-checks the session too', async () => {
    const client = createQueryClient();
    client.setQueryData(SESSION_KEY, 'signed-in');
    await client
      .getMutationCache()
      .build(client, {
        mutationFn: () => Promise.reject(new ApiError(401, 'Unauthorized', 'Sign in to continue.')),
      })
      .execute(undefined)
      .catch(() => undefined);
    expect(client.getQueryState(SESSION_KEY)?.isInvalidated).toBe(true);
  });
});
