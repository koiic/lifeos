import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Skeleton } from './Skeleton';

afterEach(cleanup);

describe('Skeleton (spec 5.5; plan 5.5 loading state)', () => {
  it('announces loading once; the shapes are decorative', async () => {
    const { container } = render(
      <Skeleton label="Loading today" shapes={['line', 'line', 'block', 'circle']} />,
    );
    const status = screen.getByRole('status', { name: 'Loading today' });
    // Not aria-busy: a busy live region holds its announcement, and this one never stops being busy.
    expect(status.hasAttribute('aria-busy')).toBe(false);
    const shapes = status.querySelectorAll('[data-shape]');
    expect(shapes).toHaveLength(4);
    for (const shape of shapes) expect(shape.getAttribute('aria-hidden')).toBe('true');
    // Also real text, for screen readers that skip a status region's aria-label.
    expect(status.textContent).toBe('Loading today');
    await expectNoAxeViolations(container);
  });
});
