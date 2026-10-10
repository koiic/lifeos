import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import { expectNoAxeViolations } from '../testing/axe';
import { StreakBadge } from './StreakBadge';

afterEach(() => {
  cleanup();
});

describe('[TOD-5] StreakBadge renders as a Sticker Book badge from 3 days', () => {
  it('does not render when streak is less than 3 days', () => {
    const { container: c0 } = render(<StreakBadge days={0} />);
    expect(c0.firstChild).toBeNull();

    const { container: c1 } = render(<StreakBadge days={1} />);
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(<StreakBadge days={2} />);
    expect(c2.firstChild).toBeNull();
  });

  it('renders correctly for 3 days and displays copy and aria-label', () => {
    render(<StreakBadge days={3} />);
    const badge = screen.getByRole('status');
    expect(badge).toBeDefined();
    expect(badge.getAttribute('aria-label')).toBe(copy.today.streakBadgeAria(3));
    expect(screen.getByText(copy.today.streak(3))).toBeDefined();
  });

  it('applies wiggle animation on milestone days (3, 7, 14, 30) but not other days', () => {
    const { rerender } = render(<StreakBadge days={3} />);
    expect(screen.getByRole('status').className).toContain('wiggle');

    rerender(<StreakBadge days={4} />);
    expect(screen.getByRole('status').className).not.toContain('wiggle');

    rerender(<StreakBadge days={7} />);
    expect(screen.getByRole('status').className).toContain('wiggle');

    rerender(<StreakBadge days={10} />);
    expect(screen.getByRole('status').className).not.toContain('wiggle');

    rerender(<StreakBadge days={14} />);
    expect(screen.getByRole('status').className).toContain('wiggle');

    rerender(<StreakBadge days={30} />);
    expect(screen.getByRole('status').className).toContain('wiggle');
  });

  it('passes axe accessibility checks in both themes', async () => {
    const { container, rerender } = render(
      <div data-theme="sorbet">
        <StreakBadge days={5} />
      </div>,
    );
    await expectNoAxeViolations(container);

    rerender(
      <div data-theme="night">
        <StreakBadge days={5} />
      </div>,
    );
    await expectNoAxeViolations(container);
  });
});
