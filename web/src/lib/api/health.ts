import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { formatIsoDate, nowIso } from '../dates';
import { api, type components } from './index';

export type CalendarDay = components['schemas']['CalendarDay'];
export type CalendarMonthResponse = components['schemas']['CalendarMonthResponse'];
export type PeriodActionResponse = components['schemas']['PeriodActionResponse'];

export function calendarMonthKey(month?: string) {
  return ['calendar', month ?? 'current'] as const;
}

/**
 * Fetch calendar month view data (spec 5.2, 9.2, 11.4, CSC-3).
 */
export function useCalendarMonth(month?: string) {
  return useQuery({
    queryKey: calendarMonthKey(month),
    queryFn: async (): Promise<CalendarMonthResponse> => {
      const query = month ? { month } : undefined;
      return api.request('GET', '/api/v1/health/calendar', undefined, {}, {}, query);
    },
  });
}

/**
 * Start a period in one tap (spec 4.5, 9.2, PER-1).
 * Sets flow Medium on specified date (defaults to today).
 */
export function useStartPeriod() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      date,
    }: { date?: string | undefined } = {}): Promise<PeriodActionResponse> => {
      const targetDate = date ?? formatIsoDate(nowIso());
      return api.request('POST', '/api/v1/health/period/start', { date: targetDate });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['cycle'] });
      queryClient.invalidateQueries({ queryKey: ['today'] });
      queryClient.invalidateQueries({ queryKey: ['dailyLog'] });
      queryClient.invalidateQueries({ queryKey: ['dailyLogs'] });
    },
  });
}

/**
 * End a period in one tap (spec 4.5, 9.2, PER-1, PER-4).
 * Confirms last flow day (defaults to today).
 */
export function useEndPeriod() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      date,
    }: { date?: string | undefined } = {}): Promise<PeriodActionResponse> => {
      const targetDate = date ?? formatIsoDate(nowIso());
      return api.request('POST', '/api/v1/health/period/end', { date: targetDate });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['cycle'] });
      queryClient.invalidateQueries({ queryKey: ['today'] });
      queryClient.invalidateQueries({ queryKey: ['dailyLog'] });
      queryClient.invalidateQueries({ queryKey: ['dailyLogs'] });
    },
  });
}
