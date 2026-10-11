import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { CycleRing, MiniRing } from './CycleRing';

describe('CycleRing (CSC-1)', () => {
  afterEach(() => {
    cleanup();
  });
  it('[CSC-1] renders accessible aria text for current cycle day and phase', () => {
    render(
      <CycleRing
        cycleLength={28}
        periodDays={5}
        fertileStart={12}
        fertileEnd={17}
        today={14}
        phase="fertile_window"
      />,
    );

    const svg = screen.getByRole('img');
    expect(svg).toBeDefined();
    expect(svg.getAttribute('aria-label')).toBe('Day 14 of 28, Fertile window');
    expect(screen.getByText('14')).toBeDefined();
    expect(screen.getByText('Fertile window')).toBeDefined();
  });

  it('[CSC-1] renders menstrual phase aria text during period', () => {
    render(<CycleRing cycleLength={28} periodDays={5} today={2} phase="menstrual" />);

    const svg = screen.getByRole('img');
    expect(svg.getAttribute('aria-label')).toBe('Day 2 of 28, Menstrual phase');
    expect(screen.getByText('2')).toBeDefined();
    expect(screen.getByText('Menstrual phase')).toBeDefined();
  });

  it('[CSC-1] renders accessible aria text for waiting state', () => {
    render(<CycleRing cycleLength={28} state="waiting" />);

    const svg = screen.getByRole('img');
    expect(svg.getAttribute('aria-label')).toBe('Waiting for cycle to return');
    expect(screen.getByText('Waiting')).toBeDefined();
  });

  it('[CSC-1] renders accessible aria text for no_data state', () => {
    render(<CycleRing cycleLength={28} state="no_data" />);

    const svg = screen.getByRole('img');
    expect(svg.getAttribute('aria-label')).toBe('No cycle data');
    expect(screen.getByText('—')).toBeDefined();
  });

  it('[CSC-1] renders period arc, fertile arc, and today marker', () => {
    const { container } = render(
      <CycleRing cycleLength={28} periodDays={5} fertileStart={12} fertileEnd={17} today={14} />,
    );

    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(2); // fertileArc + periodArc

    const circles = container.querySelectorAll('circle');
    expect(circles.length).toBe(2); // track + todayMarker
  });

  it('[CSC-1] omits fertile arc when not in fertile range', () => {
    const { container } = render(<CycleRing cycleLength={28} periodDays={5} today={3} />);

    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(1); // periodArc only
  });

  it('[CSC-1] MiniRing renders compact variant without center text', () => {
    render(<MiniRing cycleLength={28} periodDays={5} today={8} />);

    const svg = screen.getByRole('img');
    expect(svg).toBeDefined();
    expect(svg.getAttribute('aria-label')).toBe('Day 8 of 28');
    expect(screen.queryByText('Day')).toBeNull();
  });

  it('[CSC-1] passes axe accessibility checks', async () => {
    const { container } = render(
      <CycleRing
        cycleLength={28}
        periodDays={5}
        fertileStart={12}
        fertileEnd={17}
        today={14}
        phase="fertile_window"
      />,
    );

    await expectNoAxeViolations(container);
  });
});
