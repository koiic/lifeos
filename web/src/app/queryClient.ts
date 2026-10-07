import { QueryClient } from '@tanstack/react-query';

/** Spec 11.4: 30 s for Today and cycle queries, 5 min for lists. */
export const STALE_TIME = {
  today: 30 * 1000,
  cycle: 30 * 1000,
  list: 5 * 60 * 1000,
} as const;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: STALE_TIME.list,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
      },
    },
  });
}
