import 'fake-indexeddb/auto';
import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearCryptoKey } from './crypto';
import {
  clearQueryCache,
  restoreQueryCache,
  saveQueryCache,
  setupQueryCachePersistence,
} from './persister';

describe('[CHK-5] query cache persistence', () => {
  let queryClient: QueryClient;

  beforeEach(async () => {
    await clearQueryCache();
    await clearCryptoKey();
    queryClient = new QueryClient();
  });

  it('encrypts and persists query cache to IndexedDB and restores it', async () => {
    queryClient.setQueryData(['today', '2026-10-10'], { greeting: 'morning', streak: 4 });

    await saveQueryCache(queryClient);

    const freshClient = new QueryClient();
    expect(freshClient.getQueryData(['today', '2026-10-10'])).toBeUndefined();

    const restored = await restoreQueryCache(freshClient);
    expect(restored).toBe(true);

    const cached = freshClient.getQueryData(['today', '2026-10-10']);
    expect(cached).toEqual({ greeting: 'morning', streak: 4 });
  });

  it('clears query cache', async () => {
    queryClient.setQueryData(['dailyLog', '2026-10-10'], { mood: 5 });
    await saveQueryCache(queryClient);

    await clearQueryCache();

    const freshClient = new QueryClient();
    const restored = await restoreQueryCache(freshClient);
    expect(restored).toBe(false);
    expect(freshClient.getQueryData(['dailyLog', '2026-10-10'])).toBeUndefined();
  });

  it('subscribes to query cache changes and persists', async () => {
    const cleanup = setupQueryCachePersistence(queryClient, 10);

    queryClient.setQueryData(['me'], { profile: { display_name: 'Zee' } });

    // Wait for debounced persist
    await new Promise((resolve) => setTimeout(resolve, 50));

    const freshClient = new QueryClient();
    const restored = await restoreQueryCache(freshClient);
    expect(restored).toBe(true);
    expect(freshClient.getQueryData(['me'])).toEqual({ profile: { display_name: 'Zee' } });

    cleanup();
  });
});
