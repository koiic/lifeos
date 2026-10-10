import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import type { CalendarDay } from '../../lib/api/health';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { MonthCalendar } from './MonthCalendar';

const sampleDays: CalendarDay[] = [
  {
    date: '2026-10-01',
    flow: 'medium',
    has_log: true,
    fertile: false,
    predicted: false,
  },
  {
    date: '2026-10-02',
    flow: 'light',
    has_log: true,
    fertile: false,
    predicted: false,
  },
  {
    date: '2026-10-03',
    flow: 'none',
    has_log: true,
    fertile: false,
    predicted: false,
  },
  {
    date: '2026-10-14',
    flow: null,
    has_log: false,
    fertile: true,
    predicted: false,
  },
  {
    date: '2026-10-28',
    flow: null,
    has_log: false,
    fertile: false,
    predicted: true,
  },
];

describe('MonthCalendar (CSC-3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('[CSC-3] renders month heading and 7 weekday column headers', () => {
    render(
      <MonthCalendar
        month="2026-10"
        days={sampleDays}
        onPrevMonth={vi.fn()}
        onNextMonth={vi.fn()}
        onSelectDate={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { level: 2, name: /October 2026/i })).toBeDefined();
    expect(screen.getByText('Mon')).toBeDefined();
    expect(screen.getByText('Sun')).toBeDefined();
  });

  it('[CSC-3] renders period days, predicted days, fertile days, and check-in dots', () => {
    render(
      <MonthCalendar
        month="2026-10"
        days={sampleDays}
        onPrevMonth={vi.fn()}
        onNextMonth={vi.fn()}
        onSelectDate={vi.fn()}
      />,
    );

    // Period day 1 October has medium flow
    const day1 = screen.getByRole('button', { name: /^1 October 2026.*medium/i });
    expect(day1).toBeDefined();
    expect(day1.getAttribute('data-period')).toBe('true');

    // Fertile day 14 October
    const day14 = screen.getByRole('button', { name: /^14 October 2026.*fertile/i });
    expect(day14).toBeDefined();
    expect(day14.getAttribute('data-fertile')).toBe('true');

    // Predicted day 28 October
    const day28 = screen.getByRole('button', { name: /^28 October 2026.*predicted/i });
    expect(day28).toBeDefined();
    expect(day28.getAttribute('data-predicted')).toBe('true');
  });

  it('[CSC-3] navigates previous and next month on button click', () => {
    const onPrevMonth = vi.fn();
    const onNextMonth = vi.fn();

    render(
      <MonthCalendar
        month="2026-10"
        days={sampleDays}
        onPrevMonth={onPrevMonth}
        onNextMonth={onNextMonth}
        onSelectDate={vi.fn()}
      />,
    );

    const prevBtn = screen.getByRole('button', { name: copy.health.calendar.prevMonth });
    const nextBtn = screen.getByRole('button', { name: copy.health.calendar.nextMonth });

    fireEvent.click(prevBtn);
    expect(onPrevMonth).toHaveBeenCalledOnce();

    fireEvent.click(nextBtn);
    expect(onNextMonth).toHaveBeenCalledOnce();
  });

  it('[CSC-3] triggers onSelectDate when a day is clicked', () => {
    const onSelectDate = vi.fn();

    render(
      <MonthCalendar
        month="2026-10"
        days={sampleDays}
        onPrevMonth={vi.fn()}
        onNextMonth={vi.fn()}
        onSelectDate={onSelectDate}
      />,
    );

    const day1 = screen.getByRole('button', { name: /^1 October 2026/i });
    fireEvent.click(day1);

    expect(onSelectDate).toHaveBeenCalledWith('2026-10-01');
  });

  it('[CSC-3] axe clean in Sorbet and Night Garden themes', async () => {
    const { container } = render(
      <MonthCalendar
        month="2026-10"
        days={sampleDays}
        onPrevMonth={vi.fn()}
        onNextMonth={vi.fn()}
        onSelectDate={vi.fn()}
      />,
    );

    await expectNoAxeViolations(container);

    document.documentElement.setAttribute('data-theme', 'dark');
    await expectNoAxeViolations(container);
    document.documentElement.removeAttribute('data-theme');
  });
});
