// Symptoms API hooks (spec 9.2, CHK-3).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type components } from './index';

export type Symptom = components['schemas']['Symptom'];
export type SymptomCreateIn = components['schemas']['SymptomCreateIn'];
export type SymptomUpdateIn = components['schemas']['SymptomUpdateIn'];

export const SYMPTOMS_KEY = ['symptoms'] as const;

export function useSymptoms(includeArchived = false) {
  return useQuery({
    queryKey: [...SYMPTOMS_KEY, { includeArchived }],
    queryFn: async (): Promise<Symptom[]> => {
      const query: Record<string, string> = includeArchived ? { include_archived: 'true' } : {};
      return api.request('GET', '/api/v1/symptoms', undefined, query);
    },
  });
}

export function useCreateSymptom() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: SymptomCreateIn): Promise<Symptom> => {
      return api.request('POST', '/api/v1/symptoms', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYMPTOMS_KEY });
    },
  });
}

export function useArchiveSymptom() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.request('DELETE', '/api/v1/symptoms/{symptom_id}', undefined, {
        symptom_id: id,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYMPTOMS_KEY });
    },
  });
}
