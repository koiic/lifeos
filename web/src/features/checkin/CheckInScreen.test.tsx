import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as meApi from '../../lib/me/me';
import { CheckInScreen } from './CheckInScreen';

afterEach(cleanup);

// Mock CheckInSheet to verify props passed from screen
vi.mock('./CheckInSheet', () => ({
  CheckInSheet: ({ open, date }: { open: boolean; date: string }) => (
    <div data-testid="checkin-sheet" data-open={open} data-date={date}>
      CheckInSheet for {date}
    </div>
  ),
}));

function renderWithProviders(ui: ReactNode, initialEntries = ['/checkin']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CheckInScreen (CHK-1)', () => {
  it('passes query param date to CheckInSheet', () => {
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: { profile: { timezone: 'Europe/London' } },
      isSuccess: true,
    } as unknown as ReturnType<typeof meApi.useMe>);

    renderWithProviders(<CheckInScreen />, ['/checkin?date=2026-10-15']);

    const sheet = screen.getByTestId('checkin-sheet');
    expect(sheet.dataset.date).toBe('2026-10-15');
    expect(sheet.dataset.open).toBe('true');
  });

  it('defaults date to today in user timezone if not provided', () => {
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: { profile: { timezone: 'Europe/London' } },
      isSuccess: true,
    } as unknown as ReturnType<typeof meApi.useMe>);

    renderWithProviders(<CheckInScreen />, ['/checkin']);

    const sheet = screen.getByTestId('checkin-sheet');
    expect(sheet.dataset.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(sheet.dataset.open).toBe('true');
  });
});
