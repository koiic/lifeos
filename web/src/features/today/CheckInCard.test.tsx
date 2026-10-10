import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import type { CheckinState, DailyLog } from '../../lib/api';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { CheckInCard } from './CheckInCard';

const t = copy.today.checkinCard;
const tm = copy.checkin.mood;

afterEach(() => {
  cleanup();
});

describe('[TOD-3] CheckInCard component states and interactions', () => {
  const uncompleted: CheckinState = {
    done: false,
    log: null,
  };

  const sampleLog: DailyLog = {
    id: '0192f1c4-1111-7000-8000-000000000001',
    date: '2026-10-08',
    mood: 4,
    energy: 3,
    sleep_hours: 7.5,
    flow: 'medium',
    discharge: null,
    bbt_c: null,
    intimacy: null,
    note: 'Great morning',
    symptom_ids: ['s1', 's2'],
    checkin_ms: 12000,
    client_updated_at: '2026-10-08T08:00:00Z',
    created_at: '2026-10-08T08:00:00Z',
    updated_at: '2026-10-08T08:00:00Z',
  };

  const completed: CheckinState = {
    done: true,
    log: sampleLog,
  };

  it('renders uncompleted state with mood buttons and prompt', () => {
    const onSelectMood = vi.fn();
    const onOpenCheckIn = vi.fn();

    render(
      <CheckInCard
        checkin={uncompleted}
        onSelectMood={onSelectMood}
        onOpenCheckIn={onOpenCheckIn}
      />,
    );

    expect(screen.getByRole('heading', { level: 2, name: t.title })).toBeDefined();
    expect(screen.getByText(t.prompt)).toBeDefined();

    // 5 mood buttons
    expect(screen.getByRole('button', { name: tm.bright })).toBeDefined();
    expect(screen.getByRole('button', { name: tm.good })).toBeDefined();
    expect(screen.getByRole('button', { name: tm.okay })).toBeDefined();
    expect(screen.getByRole('button', { name: tm.tired })).toBeDefined();
    expect(screen.getByRole('button', { name: tm.low })).toBeDefined();

    // Tapping a mood invokes onSelectMood
    fireEvent.click(screen.getByRole('button', { name: tm.good }));
    expect(onSelectMood).toHaveBeenCalledWith(4);

    // Tapping check-in button invokes onOpenCheckIn
    fireEvent.click(screen.getByRole('button', { name: t.checkIn }));
    expect(onOpenCheckIn).toHaveBeenCalledOnce();
  });

  it('renders completed state with summary chips and edit action', () => {
    const onSelectMood = vi.fn();
    const onOpenCheckIn = vi.fn();

    render(
      <CheckInCard checkin={completed} onSelectMood={onSelectMood} onOpenCheckIn={onOpenCheckIn} />,
    );

    expect(screen.getByRole('heading', { level: 2, name: t.doneTitle })).toBeDefined();
    expect(screen.getByTestId('completed-sticker')).toBeDefined();

    // Summary items
    expect(screen.getByTestId('summary-mood').textContent).toContain(tm.good);
    expect(screen.getByTestId('summary-energy').textContent).toBe(t.energyLabel(3));
    expect(screen.getByTestId('summary-sleep').textContent).toBe(t.sleepLabel(7.5));
    expect(screen.getByTestId('summary-flow').textContent).toBe(
      t.flowLabel(copy.checkin.flow.medium),
    );
    expect(screen.getByTestId('summary-symptoms').textContent).toBe(t.symptomsCount(2));

    // Edit button
    const editBtn = screen.getByRole('button', { name: t.edit });
    expect(editBtn).toBeDefined();
    fireEvent.click(editBtn);
    expect(onOpenCheckIn).toHaveBeenCalledOnce();
  });

  it('passes axe accessibility checks in both themes', async () => {
    const { container, rerender } = render(
      <div data-theme="sorbet">
        <CheckInCard checkin={uncompleted} onSelectMood={vi.fn()} onOpenCheckIn={vi.fn()} />
      </div>,
    );
    await expectNoAxeViolations(container);

    rerender(
      <div data-theme="night">
        <CheckInCard checkin={completed} onSelectMood={vi.fn()} onOpenCheckIn={vi.fn()} />
      </div>,
    );
    await expectNoAxeViolations(container);
  });
});
