// Daily logs API hooks (spec 9.2, CHK-1, CHK-2, PER-2).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { enqueue, flushOutbox } from '../offline';
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
    networkMode: 'always',
    mutationFn: async ({
      date,
      data,
    }: {
      date: string;
      data: DailyLogPutIn;
    }): Promise<DailyLogPutResponse> => {
      // 1. Enqueue in IndexedDB outbox (spec 11.5)
      await enqueue({
        method: 'PUT',
        path: `/api/v1/daily-logs/${date}`,
        body: data,
      });

      // 2. Optimistic update in query cache
      queryClient.setQueryData(dailyLogKey(date), (old: DailyLog | null | undefined): DailyLog => ({
        id: old?.id ?? 'optimistic',
        date,
        mood: data.mood ?? null,
        energy: data.energy ?? null,
        sleep_hours: data.sleep_hours ?? null,
        flow: data.flow ?? null,
        discharge: data.discharge ?? null,
        bbt_c: data.bbt_c ?? null,
        intimacy: data.intimacy ?? null,
        note: data.note ?? null,
        symptom_ids: data.symptom_ids ?? [],
        checkin_ms: data.checkin_ms ?? null,
        client_updated_at: data.client_updated_at,
        created_at: old?.created_at ?? data.client_updated_at,
        updated_at: data.client_updated_at,
      }));

      // 3. Flush outbox
      await flushOutbox();

      return {
        rebuild: 'not_needed',
        ...data,
      } as unknown as DailyLogPutResponse;
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
