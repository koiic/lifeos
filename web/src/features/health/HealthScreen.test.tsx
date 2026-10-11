import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as healthApi from '../../lib/api/health';
import * as meApi from '../../lib/me/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { HealthScreen } from './HealthScreen';

const t = copy.health;

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

const mockCycleData: healthApi.CycleStateResponse = {
  cycle_day: 14,
  latest_start: '2026-09-24',
  phase: 'fertile_window',
  state: 'upcoming',
  prediction: {
    predicted_start: '2026-10-23',
    range_low: '2026-10-22',
    range_high: '2026-10-24',
    confidence: 'medium',
    ovulation_est: '2026-10-09',
    fertile_start: '2026-10-04',
    fertile_end: '2026-10-10',
    n_cycles: 4,
    mean_len: 28.75,
    sd_len: 0.5,
    mean_period_len: 5,
    algorithm_version: 'calendar-1.0',
    suppressed_reason: null,
  },
  notes: [],
  pending_prompt: null,
  mode: 'standard',
};

describe('HealthScreen / Cycle screen (CSC-1, CSC-2)', () => {
  const mockConfirm = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(meApi, 'useMe').mockReturnValue({
      data: mockMe,
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof meApi.useMe>);

    vi.spyOn(healthApi, 'useCycleState').mockReturnValue({
      data: mockCycleData,
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useCycleState>);

    vi.spyOn(healthApi, 'useConfirmPeriodStart').mockReturnValue({
      mutate: mockConfirm,
      isPending: false,
    } as unknown as ReturnType<typeof healthApi.useConfirmPeriodStart>);

    vi.spyOn(healthApi, 'useStartPeriod').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof healthApi.useStartPeriod>);

    vi.spyOn(healthApi, 'useEndPeriod').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof healthApi.useEndPeriod>);
  });

  afterEach(() => {
    cleanup();
  });

  it('[CSC-1] renders CycleRing with day 14 and fertile window', () => {
    renderRoute(<HealthScreen />, {
      path: '/health/cycle',
      url: '/health/cycle',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.title })).toBeDefined();

    // CycleRing accessible image
    const ring = screen.getByRole('img');
    expect(ring.getAttribute('aria-label')).toBe('Day 14 of 29, Fertile window');

    // Navigation links to Calendar and History
    expect(screen.getByRole('link', { name: t.calendarTab })).toBeDefined();
    expect(screen.getByRole('link', { name: t.historyTab })).toBeDefined();
  });

  it('[CSC-2] renders PredictionCard and derived state copy', () => {
    renderRoute(<HealthScreen />, {
      path: '/health/cycle',
      url: '/health/cycle',
    });

    // Prediction card range and based on cycles
    expect(screen.getByText('22 Oct – 24 Oct')).toBeDefined();
    expect(screen.getByText('Based on 4 cycles')).toBeDefined();

    // Derived state banner
    expect(screen.getByText(/Period in about/)).toBeDefined();
  });

  it('[CSC-1] renders and handles pending new period prompt confirmation', () => {
    vi.spyOn(healthApi, 'useCycleState').mockReturnValue({
      data: {
        ...mockCycleData,
        pending_prompt: {
          kind: 'new_period',
          date: '2026-10-02',
        },
      },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useCycleState>);

    renderRoute(<HealthScreen />, {
      path: '/health/cycle',
      url: '/health/cycle',
    });

    expect(screen.getByText(t.cycle.pendingPrompt.title)).toBeDefined();

    const yesButton = screen.getByRole('button', { name: t.cycle.pendingPrompt.confirmYes });
    fireEvent.click(yesButton);

    expect(mockConfirm).toHaveBeenCalledWith({
      date: '2026-10-02',
      is_new_period: true,
    });
  });

  it('[CSC-1] axe clean in Sorbet and Night Garden themes', async () => {
    const { container } = renderRoute(<HealthScreen />, {
      path: '/health/cycle',
      url: '/health/cycle',
    });

    await expectNoAxeViolations(container);

    document.documentElement.setAttribute('data-theme', 'dark');
    await expectNoAxeViolations(container);
    document.documentElement.removeAttribute('data-theme');
  });
});
