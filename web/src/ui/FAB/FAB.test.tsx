import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { FAB } from './FAB';

afterEach(cleanup);

describe('FAB (spec 5.5; 5.8 icon-only controls have aria-label)', () => {
  it('is an icon button named by its label', async () => {
    const onClick = vi.fn();
    const { container } = render(<FAB label="Add" onClick={onClick} />);
    const fab = screen.getByRole('button', { name: 'Add' });
    expect(fab.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    fireEvent.click(fab);
    expect(onClick).toHaveBeenCalledOnce();
    await expectNoAxeViolations(container);
  });
});
