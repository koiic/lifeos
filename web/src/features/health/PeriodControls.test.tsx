import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as api from '../../lib/api';
import { PeriodControls } from './PeriodControls';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'TestQueryClientWrapper';
  return Wrapper;
}

describe('PeriodControls (PER-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('[PER-1] renders "Period started" and triggers startPeriod on tap', () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      date: '2026-10-10',
      flow: 'medium',
      message: 'Period started',
      rebuild: 'queued',
    });
    vi.spyOn(api, 'useStartPeriod').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof api.useStartPeriod>);
    vi.spyOn(api, 'useEndPeriod').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof api.useEndPeriod>);

    render(<PeriodControls isOngoing={false} />, { wrapper: createWrapper() });

    const startBtn = screen.getByRole('button', { name: copy.health.period.started });
    expect(startBtn).toBeDefined();

    fireEvent.click(startBtn);
    expect(mutateAsync).toHaveBeenCalled();
  });

  it('[PER-1] renders "Period ended" when period is ongoing and triggers endPeriod on tap', () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      date: '2026-10-10',
      flow: 'none',
      message: 'Period ended',
      rebuild: 'queued',
    });
    vi.spyOn(api, 'useStartPeriod').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof api.useStartPeriod>);
    vi.spyOn(api, 'useEndPeriod').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof api.useEndPeriod>);

    render(<PeriodControls isOngoing={true} ongoingStartDate="2026-10-06" />, {
      wrapper: createWrapper(),
    });

    const endBtn = screen.getByRole('button', { name: copy.health.period.ended });
    expect(endBtn).toBeDefined();

    fireEvent.click(endBtn);
    expect(mutateAsync).toHaveBeenCalled();
  });
});
