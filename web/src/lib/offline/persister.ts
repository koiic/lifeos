import { type DehydratedState, dehydrate, hydrate, type QueryClient } from '@tanstack/react-query';

import { decrypt, encrypt } from './crypto';
import { getDB } from './db';

const CACHE_KEY = 'query_cache_v1';
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000; // 14 days (spec 11.4)

/** Spec 11.4: whitelisted query keys persisted to IndexedDB */
export const PERSISTED_QUERY_ROOTS = new Set([
  'me',
  'today',
  'dailyLog',
  'dailyLogs',
  'cycle',
  'cycles',
  'calendar',
  'meds',
  'doses',
  'events',
  'people',
  'tasks',
  'notes',
  'inbox',
  'insights',
]);

export async function saveQueryCache(queryClient: QueryClient): Promise<void> {
  const dehydrated = dehydrate(queryClient, {
    shouldDehydrateQuery: (query) =>
      query.state.status === 'success' &&
      typeof query.queryKey[0] === 'string' &&
      PERSISTED_QUERY_ROOTS.has(query.queryKey[0]),
  });

  const serialized = JSON.stringify(dehydrated);
  const encrypted = await encrypt(serialized);

  const db = await getDB();
  await db.put('query_cache', {
    id: CACHE_KEY,
    iv: encrypted.iv,
    ciphertext: encrypted.ciphertext,
    updated_at: new Date().toISOString(),
  });
}

export async function restoreQueryCache(queryClient: QueryClient): Promise<boolean> {
  try {
    const db = await getDB();
    const entry = await db.get('query_cache', CACHE_KEY);
    if (!entry) {
      return false;
    }

    const age = Date.now() - new Date(entry.updated_at).getTime();
    if (age > MAX_AGE_MS) {
      await db.delete('query_cache', CACHE_KEY);
      return false;
    }

    const decrypted = await decrypt({ iv: entry.iv, ciphertext: entry.ciphertext });
    const dehydrated = JSON.parse(decrypted) as DehydratedState;
    hydrate(queryClient, dehydrated);
    return true;
  } catch {
    return false;
  }
}

export async function clearQueryCache(): Promise<void> {
  const db = await getDB();
  await db.delete('query_cache', CACHE_KEY);
}

export function setupQueryCachePersistence(
  queryClient: QueryClient,
  debounceMs = 1000,
): () => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const unsubscribe = queryClient.getQueryCache().subscribe(() => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      void saveQueryCache(queryClient);
    }, debounceMs);
  });

  return () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    unsubscribe();
  };
}
