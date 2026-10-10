import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as dailyLogsApi from '../../lib/api/dailyLogs';
import * as meApi from '../../lib/me/me';
import { meBody } from '../../lib/testing/me';
import { CheckInSheet } from './CheckInSheet';

afterEach(cleanup);

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('[CHK-1][CHK-3][CHK-4][PER-2] CheckInSheet', () => {
  const mockSettings = meBody().settings;

  it('renders check-in sheet with pickers and submits data', async () => {
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: { settings: mockSettings },
      isSuccess: true,
    } as unknown as ReturnType<typeof meApi.useMe>);

    vi.spyOn(dailyLogsApi, 'useDailyLog').mockReturnValue({
      data: null,
      isSuccess: true,
      isPending: false,
    } as unknown as ReturnType<typeof dailyLogsApi.useDailyLog>);

    const mockMutate = vi.fn().mockResolvedValue({});
    vi.spyOn(dailyLogsApi, 'useSaveDailyLog').mockReturnValue({
      mutateAsync: mockMutate,
      isPending: false,
    } as unknown as ReturnType<typeof dailyLogsApi.useSaveDailyLog>);

    const onClose = vi.fn();
    const onSaved = vi.fn();

    renderWithClient(
      <CheckInSheet open={true} date="2026-10-10" onClose={onClose} onSaved={onSaved} />,
    );

    expect(screen.getByRole('dialog', { name: /daily check-in/i })).toBeDefined();

    // Select mood: Good (4)
    fireEvent.click(screen.getByRole('radio', { name: /good/i }));

    // Select energy: 4
    fireEvent.click(screen.getByRole('radio', { name: '4' }));

    // Adjust sleep: increment to 0.5
    fireEvent.click(screen.getByRole('button', { name: /increase sleep/i }));

    // Select flow: Medium
    fireEvent.click(screen.getByRole('radio', { name: /medium/i }));

    // Add note
    const noteArea = screen.getByLabelText(/note/i);
    fireEvent.change(noteArea, { target: { value: 'Feeling energetic today' } });

    // Submit form
    const saveBtn = screen.getByRole('button', { name: /save check-in/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledTimes(1);
    });

    const callArgs = mockMutate.mock.calls[0]?.[0];
    expect(callArgs).toBeDefined();
    if (!callArgs) return;
    expect(callArgs.date).toBe('2026-10-10');
    expect(callArgs.data.mood).toBe(4);
    expect(callArgs.data.energy).toBe(4);
    expect(callArgs.data.sleep_hours).toBe(7.5);
    expect(callArgs.data.flow).toBe('medium');
    expect(callArgs.data.note).toBe('Feeling energetic today');
    expect(callArgs.data.checkin_ms).toBeGreaterThanOrEqual(0);
    expect(typeof callArgs.data.client_updated_at).toBe('string');

    expect(onSaved).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('pre-fills existing daily log values', () => {
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: { settings: mockSettings },
      isSuccess: true,
    } as unknown as ReturnType<typeof meApi.useMe>);

    vi.spyOn(dailyLogsApi, 'useDailyLog').mockReturnValue({
      data: {
        date: '2026-10-10',
        mood: 5,
        energy: 3,
        sleep_hours: 8,
        flow: 'light',
        symptom_ids: ['sym-1'],
        note: 'Existing notes here',
        bbt_c: null,
        discharge: null,
        intimacy: null,
      },
      isSuccess: true,
      isPending: false,
    } as unknown as ReturnType<typeof dailyLogsApi.useDailyLog>);

    vi.spyOn(dailyLogsApi, 'useSaveDailyLog').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof dailyLogsApi.useSaveDailyLog>);

    renderWithClient(<CheckInSheet open={true} date="2026-10-10" onClose={() => {}} />);

    const bright = screen.getByRole('radio', { name: /bright/i });
    expect(bright.getAttribute('aria-checked')).toBe('true');

    const energy3 = screen.getByRole('radio', { name: '3' });
    expect(energy3.getAttribute('aria-checked')).toBe('true');

    expect(screen.getByText('8 hrs')).toBeDefined();

    const lightFlow = screen.getByRole('radio', { name: /light/i });
    expect((lightFlow as HTMLInputElement).checked).toBe(true);

    const noteArea = screen.getByLabelText(/note/i) as HTMLTextAreaElement;
    expect(noteArea.value).toBe('Existing notes here');
  });

  it('displays note character count and prevents exceeding 2000 chars', () => {
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: { settings: mockSettings },
      isSuccess: true,
    } as unknown as ReturnType<typeof meApi.useMe>);

    vi.spyOn(dailyLogsApi, 'useDailyLog').mockReturnValue({
      data: null,
      isSuccess: true,
      isPending: false,
    } as unknown as ReturnType<typeof dailyLogsApi.useDailyLog>);

    vi.spyOn(dailyLogsApi, 'useSaveDailyLog').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof dailyLogsApi.useSaveDailyLog>);

    renderWithClient(<CheckInSheet open={true} date="2026-10-10" onClose={() => {}} />);

    expect(screen.getByText('2000 characters left')).toBeDefined();

    const noteArea = screen.getByLabelText(/note/i);
    fireEvent.change(noteArea, { target: { value: 'Hello' } });
    expect(screen.getByText('1995 characters left')).toBeDefined();

    // Trying to enter 2001 chars will be rejected by handler
    const longText = 'a'.repeat(2001);
    fireEvent.change(noteArea, { target: { value: longText } });
    // Still 1995 because 2001 was ignored
    expect(screen.getByText('1995 characters left')).toBeDefined();
  });
});
