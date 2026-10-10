import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as api from '../../lib/api';
import * as meApi from '../../lib/me/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { CycleCalendarScreen } from './CycleCalendarScreen';

const mockMe = {
  profile: {
    display_name: 'Zee',
    timezone: 'Europe/London',
    week_start: 'monday',
  },
  settings: {
    optional_fields: { bbt: false, discharge: false, intimacy: false },
  },
};

const mockCalendarDays: api.CalendarDay[] = [
  {
    date: '2026-10-05',
    flow: 'none',
    has_log: false,
    fertile: false,
    predicted: false,
  },
  {
    date: '2026-10-06',
    flow: 'medium',
    has_log: true,
    fertile: false,
    predicted: false,
  },
];

describe('CycleCalendarScreen (PER-3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: mockMe,
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof meApi.useMe>);

    vi.spyOn(api, 'useCalendarMonth').mockReturnValue({
      data: { month: '2026-10', days: mockCalendarDays },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof api.useCalendarMonth>);

    vi.spyOn(api, 'useStartPeriod').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof api.useStartPeriod>);

    vi.spyOn(api, 'useEndPeriod').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof api.useEndPeriod>);
  });

  afterEach(() => {
    cleanup();
  });

  it('[PER-3] tapping a past calendar day triggers onSelectDate callback', () => {
    const onSelectDate = vi.fn();
    renderRoute(<CycleCalendarScreen initialMonth="2026-10" onSelectDate={onSelectDate} />, {
      path: '/health/calendar',
      url: '/health/calendar',
    });

    expect(
      screen.getByRole('heading', { level: 1, name: copy.health.calendar.title }),
    ).toBeDefined();

    const day5 = screen.getByRole('button', { name: /^5 October 2026/i });
    fireEvent.click(day5);

    expect(onSelectDate).toHaveBeenCalledWith('2026-10-05');
  });

  it('[PER-3] tapping a calendar day navigates to /checkin with date query param', () => {
    const { router } = renderRoute(<CycleCalendarScreen initialMonth="2026-10" />, {
      path: '/health/calendar',
      url: '/health/calendar',
    });

    const day5 = screen.getByRole('button', { name: /^5 October 2026/i });
    fireEvent.click(day5);

    expect(router.state.location.pathname).toBe('/checkin');
    expect(router.state.location.search).toBe('?date=2026-10-05');
  });

  it('[PER-3] axe clean in Sorbet and Night Garden themes', async () => {
    const { container } = renderRoute(<CycleCalendarScreen initialMonth="2026-10" />, {
      path: '/health/calendar',
      url: '/health/calendar',
    });

    await expectNoAxeViolations(container);

    document.documentElement.setAttribute('data-theme', 'dark');
    await expectNoAxeViolations(container);
    document.documentElement.removeAttribute('data-theme');
  });
});
