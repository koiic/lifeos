import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as symptomsApi from '../../lib/api/symptoms';
import { SymptomPicker } from './SymptomPicker';

afterEach(cleanup);

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('SymptomPicker', () => {
  it('renders symptom chips and allows toggling selection', () => {
    vi.spyOn(symptomsApi, 'useSymptoms').mockReturnValue({
      data: [
        {
          id: 'sym-1',
          name: 'Cramps',
          category: 'pain',
          sort_order: 1,
          archived: false,
          created_at: '',
        },
        {
          id: 'sym-2',
          name: 'Headache',
          category: 'pain',
          sort_order: 2,
          archived: false,
          created_at: '',
        },
      ],
    } as unknown as ReturnType<typeof symptomsApi.useSymptoms>);

    const onChange = vi.fn();
    renderWithClient(<SymptomPicker selectedIds={['sym-1']} onChange={onChange} />);

    const cramps = screen.getByRole('button', { name: /cramps/i });
    expect(cramps.getAttribute('aria-pressed')).toBe('true');

    const headache = screen.getByRole('button', { name: /headache/i });
    expect(headache.getAttribute('aria-pressed')).toBe('false');

    // Clicking unselected adds it
    fireEvent.click(headache);
    expect(onChange).toHaveBeenCalledWith(['sym-1', 'sym-2']);

    // Clicking selected removes it
    fireEvent.click(cramps);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('allows adding a custom symptom', async () => {
    vi.spyOn(symptomsApi, 'useSymptoms').mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof symptomsApi.useSymptoms>);
    const mockCreate = vi.fn().mockResolvedValue({ id: 'sym-custom', name: 'Brain fog' });
    vi.spyOn(symptomsApi, 'useCreateSymptom').mockReturnValue({
      mutateAsync: mockCreate,
      isPending: false,
    } as unknown as ReturnType<typeof symptomsApi.useCreateSymptom>);

    const onChange = vi.fn();
    renderWithClient(<SymptomPicker selectedIds={[]} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: /add symptom/i }));
    const input = screen.getByLabelText(/symptom name/i);
    fireEvent.change(input, { target: { value: 'Brain fog' } });

    fireEvent.click(screen.getByRole('button', { name: /^add$/i }));
    expect(mockCreate).toHaveBeenCalledWith({
      name: 'Brain fog',
      category: 'other',
      sort_order: 0,
    });
  });
});
