import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { EmptyState } from './EmptyState';

afterEach(cleanup);

describe('EmptyState (spec 5.5; plan 5.5 every screen has an empty state)', () => {
  it('has a heading, a line and an optional action', async () => {
    const onClick = vi.fn();
    const { container } = render(
      <EmptyState
        icon="calendar"
        title="Nothing planned"
        body="Add an appointment and it shows here."
        action={{ label: 'Add appointment', onClick }}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Nothing planned' })).toBeDefined();
    expect(screen.getByText('Add an appointment and it shows here.')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Add appointment' }));
    expect(onClick).toHaveBeenCalledOnce();
    await expectNoAxeViolations(container);
  });

  it('works without an action', () => {
    render(<EmptyState title="All done" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
