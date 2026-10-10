import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SleepStepper } from './SleepStepper';

afterEach(cleanup);

describe('SleepStepper', () => {
  it('displays not logged when value is null', () => {
    render(<SleepStepper value={null} onChange={() => {}} />);
    expect(screen.getByText('Not logged')).toBeDefined();
  });

  it('increments and decrements sleep hours in 0.5 steps', () => {
    const onChange = vi.fn();
    const { rerender } = render(<SleepStepper value={7} onChange={onChange} />);

    expect(screen.getByText('7 hrs')).toBeDefined();

    const inc = screen.getByRole('button', { name: /increase sleep/i });
    fireEvent.click(inc);
    expect(onChange).toHaveBeenCalledWith(7.5);

    const dec = screen.getByRole('button', { name: /decrease sleep/i });
    fireEvent.click(dec);
    expect(onChange).toHaveBeenCalledWith(6.5);

    rerender(<SleepStepper value={7.5} onChange={onChange} />);
    const clear = screen.getByRole('button', { name: /clear sleep/i });
    fireEvent.click(clear);
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
