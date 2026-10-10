// Daily logs API hooks (spec 9.2, CHK-1, CHK-2, PER-2).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError, type components } from './index';

export type DailyLog = components['schemas']['DailyLog'];
export type DailyLogPutIn = components['schemas']['DailyLogPutIn'];
export type DailyLogPutResponse = components['schemas']['DailyLogPutResponse'];

export function dailyLogKey(date: string) {
  return ['dailyLog', date] as const;
}

export function useDailyLog(date: string) {
  return useQuery({
    queryKey: dailyLogKey(date),
    queryFn: async (): Promise<DailyLog | null> => {
      try {
        return await api.request('GET', '/api/v1/daily-logs/{log_date}', undefined, {
          log_date: date,
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
    enabled: Boolean(date),
  });
}

export function useSaveDailyLog() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      date,
      data,
    }: {
      date: string;
      data: DailyLogPutIn;
    }): Promise<DailyLogPutResponse> => {
      return api.request('PUT', '/api/v1/daily-logs/{log_date}', data, { log_date: date });
    },
    onSuccess: (_result, { date }) => {
      queryClient.invalidateQueries({ queryKey: dailyLogKey(date) });
      queryClient.invalidateQueries({ queryKey: ['dailyLogs'] });
      queryClient.invalidateQueries({ queryKey: ['today'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['cycle'] });
    },
  });
}
