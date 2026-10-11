import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { formatIsoDate, nowIso } from '../dates';
import { api, type components } from './index';

export type CalendarDay = components['schemas']['CalendarDay'];
export type CalendarMonthResponse = components['schemas']['CalendarMonthResponse'];
export type PeriodActionResponse = components['schemas']['PeriodActionResponse'];
export type CycleStateResponse = components['schemas']['CycleStateResponse'];
export type CyclePredictionResponse = components['schemas']['CyclePredictionResponse'];
export type CycleNote = components['schemas']['CycleNote'];
export type PendingPrompt = components['schemas']['PendingPrompt'];
export type CycleHistoryItem = components['schemas']['CycleHistoryItem'];
export type CycleExclusionIn = components['schemas']['CycleExclusionIn'];
export type PeriodStartConfirmIn = components['schemas']['PeriodStartConfirmIn'];
export type HealthProfileResponse = components['schemas']['HealthProfileResponse'];
export type HealthProfileUpdateIn = components['schemas']['HealthProfileUpdateIn'];

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

/**
 * Fetch cycle state, prediction, derived state and prompt (spec 5.2, 8.4, 9.2, CSC-1, CSC-2).
 */
export function useCycleState() {
  return useQuery({
    queryKey: ['cycle'],
    queryFn: async (): Promise<CycleStateResponse> => {
      return api.request('GET', '/api/v1/health/cycle');
    },
  });
}

/**
 * Fetch cycle history with exclusions (spec 5.2, 9.2, CSC-4, CYC-5).
 */
export function useCyclesHistory() {
  return useQuery({
    queryKey: ['cycles'],
    queryFn: async (): Promise<CycleHistoryItem[]> => {
      return api.request('GET', '/api/v1/health/cycles');
    },
  });
}

/**
 * Exclude or re-include a cycle (spec 9.2, CYC-5, CSC-4).
 */
export function useSetCycleExclusion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CycleExclusionIn): Promise<CycleHistoryItem> => {
      return (await api.request(
        'POST',
        '/api/v1/health/cycles/exclusions',
        payload,
      )) as CycleHistoryItem;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cycle'] });
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['today'] });
    },
  });
}

/**
 * Confirm whether an intra-cycle bleed is a new period (spec 8.1, 9.2, CYC-1).
 */
export function useConfirmPeriodStart() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: PeriodStartConfirmIn): Promise<CycleStateResponse> => {
      return (await api.request(
        'POST',
        '/api/v1/health/period-starts/confirm',
        payload,
      )) as CycleStateResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cycle'] });
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['today'] });
    },
  });
}

export const HEALTH_PROFILE_KEY = ['health', 'profile'] as const;

/**
 * Fetch health profile: mode, usual lengths, hints (spec 9.2, SET-4, ONB-2).
 */
export function useHealthProfile() {
  return useQuery({
    queryKey: HEALTH_PROFILE_KEY,
    queryFn: async (): Promise<HealthProfileResponse> => {
      return (await api.request('GET', '/api/v1/health/profile')) as HealthProfileResponse;
    },
  });
}

/**
 * Update health profile: mode, usual lengths, hints (spec 9.2, SET-4, ONB-2).
 */
export function useUpdateHealthProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: HealthProfileUpdateIn): Promise<HealthProfileResponse> => {
      return (await api.request('PUT', '/api/v1/health/profile', payload)) as HealthProfileResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: HEALTH_PROFILE_KEY });
      queryClient.invalidateQueries({ queryKey: ['cycle'] });
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['today'] });
      queryClient.invalidateQueries({ queryKey: ['me'] });
    },
  });
}
