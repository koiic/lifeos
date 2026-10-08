import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { ApiError } from '../lib/api';
import { SESSION_KEY } from '../lib/auth/session';

/** Spec 11.4: 30 s for Today and cycle queries, 5 min for lists. */
export const STALE_TIME = {
  today: 30 * 1000,
  cycle: 30 * 1000,
  list: 5 * 60 * 1000,
} as const;

export function createQueryClient(): QueryClient {
  // Any 401 means the session has ended (signed out elsewhere, revoked, expired): re-check it, so
  // the signed-in screens hand over to sign-in and clear her data (AUTH-5, spec 11.4).
  const recheckSession = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      void client.invalidateQueries({ queryKey: SESSION_KEY });
    }
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: recheckSession }),
    mutationCache: new MutationCache({ onError: recheckSession }),
    defaultOptions: {
      queries: {
        staleTime: STALE_TIME.list,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
      },
    },
  });
  return client;
}
