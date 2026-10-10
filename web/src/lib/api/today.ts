// Today API hooks (spec 9.3, TOD-3, TOD-5).
import { useQuery } from '@tanstack/react-query';

import { api, type components } from './index';

export type TodayResponse = components['schemas']['TodayResponse'];
export type CheckinState = components['schemas']['CheckinState'];

export function todayKey(date?: string) {
  return ['today', date ?? 'current'] as const;
}

export function useToday(date?: string) {
  return useQuery({
    queryKey: todayKey(date),
    queryFn: async (): Promise<TodayResponse> => {
      const queryParams = date ? { date } : undefined;
      return await api.request('GET', '/api/v1/today', undefined, {}, {}, queryParams);
    },
  });
}
