import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { ErrorState } from './ErrorState';

afterEach(cleanup);

describe('ErrorState (spec 5.5; plan 5.5 every screen has an error state)', () => {
  it('explains and offers a retry', async () => {
    const onRetry = vi.fn();
    const { container } = render(
      <ErrorState
        title="Couldn't load this"
        body="Check your connection."
        retry={{ label: 'Try again', onClick: onRetry }}
      />,
    );
    expect(screen.getByRole('heading', { name: "Couldn't load this" })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
    await expectNoAxeViolations(container);
  });
});
