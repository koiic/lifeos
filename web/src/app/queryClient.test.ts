import { describe, expect, it } from 'vitest';

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
});
