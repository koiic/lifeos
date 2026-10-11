import { cleanup, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as healthApi from '../../lib/api/health';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { CycleHistoryScreen } from './CycleHistoryScreen';

const t = copy.health.history;

const mockCycles: healthApi.CycleHistoryItem[] = [
  {
    seq: 1,
    start_date: '2026-07-01',
    end_date: '2026-07-28',
    length_days: 28,
    period_length_days: 5,
    is_complete: true,
    excluded: false,
    exclusion_reason: null,
    postpartum: false,
  },
  {
    seq: 2,
    start_date: '2026-07-29',
    end_date: '2026-08-27',
    length_days: 30,
    period_length_days: 5,
    is_complete: true,
    excluded: false,
    exclusion_reason: null,
    postpartum: false,
  },
  {
    seq: 3,
    start_date: '2026-08-28',
    end_date: '2026-09-08',
    length_days: 12,
    period_length_days: 3,
    is_complete: true,
    excluded: true,
    exclusion_reason: 'outlier',
    postpartum: false,
  },
];

describe('CycleHistoryScreen (CSC-4, CYC-5)', () => {
  const mockMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(healthApi, 'useCyclesHistory').mockReturnValue({
      data: mockCycles,
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useCyclesHistory>);

    vi.spyOn(healthApi, 'useSetCycleExclusion').mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as unknown as ReturnType<typeof healthApi.useSetCycleExclusion>);
  });

  afterEach(() => {
    cleanup();
  });

  it('[CSC-4] renders cycle history list and summary averages', () => {
    renderRoute(<CycleHistoryScreen />, {
      path: '/health/history',
      url: '/health/history',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.title })).toBeDefined();

    // Summary averages from included cycles (28 + 30) / 2 = 29
    expect(screen.getByText('29 days')).toBeDefined();
    expect(screen.getByText('28–30 days')).toBeDefined();
    expect(screen.getByText('5 days')).toBeDefined();

    // Cycles list
    expect(screen.getByText('Cycle 1')).toBeDefined();
    expect(screen.getByText('Cycle 2')).toBeDefined();
    expect(screen.getByText('Cycle 3')).toBeDefined();

    // Excluded badge on cycle 3
    expect(screen.getByText(t.cycleItem.excludedBadge)).toBeDefined();
    expect(screen.getByText('(outlier)')).toBeDefined();
  });

  it('[CYC-5] opens exclude dialog and confirms exclusion with reason', () => {
    renderRoute(<CycleHistoryScreen />, {
      path: '/health/history',
      url: '/health/history',
    });

    // Tap "Exclude cycle" on Cycle 1
    const excludeButtons = screen.getAllByRole('button', { name: t.cycleItem.excludeAction });
    const [firstExclude] = excludeButtons;
    expect(firstExclude).toBeDefined();
    if (firstExclude) fireEvent.click(firstExclude);

    // Dialog opens
    expect(screen.getByRole('heading', { level: 2, name: t.cycleItem.excludeTitle })).toBeDefined();
    expect(screen.getByText(t.cycleItem.excludeBody)).toBeDefined();

    // Change reason to travel
    const select = screen.getByLabelText(t.cycleItem.reasonLabel);
    fireEvent.change(select, { target: { value: 'travel' } });

    // Confirm exclusion inside dialog
    const dialog = screen.getByRole('dialog');
    const confirmButton = within(dialog).getByRole('button', { name: t.cycleItem.excludeAction });
    expect(confirmButton).toBeDefined();
    fireEvent.click(confirmButton);

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        start_date: '2026-07-01',
        excluded: true,
        reason: 'travel',
      }),
      expect.anything(),
    );
  });

  it('[CYC-5] re-includes an excluded cycle on tap', () => {
    renderRoute(<CycleHistoryScreen />, {
      path: '/health/history',
      url: '/health/history',
    });

    // Tap "Include cycle" on Cycle 3
    const includeButton = screen.getByRole('button', { name: t.cycleItem.includeAction });
    fireEvent.click(includeButton);

    expect(mockMutate).toHaveBeenCalledWith({
      start_date: '2026-08-28',
      excluded: false,
    });
  });

  it('[CSC-4] passes axe accessibility checks', async () => {
    const { container } = renderRoute(<CycleHistoryScreen />, {
      path: '/health/history',
      url: '/health/history',
    });

    await expectNoAxeViolations(container);
  });
});
