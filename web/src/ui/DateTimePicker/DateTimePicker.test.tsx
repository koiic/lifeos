import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { DateTimePicker } from './DateTimePicker';

afterEach(cleanup);

describe('DateTimePicker (spec 5.5: native inputs styled)', () => {
  it.each([
    ['date', '2026-10-08'],
    ['time', '19:00'],
    ['datetime-local', '2026-10-08T19:00'],
  ] as const)('%s is a native labelled input', async (kind, value) => {
    const onChange = vi.fn();
    const { container } = render(
      <DateTimePicker label="When" name="when" kind={kind} value="" onChange={onChange} />,
    );
    const input = screen.getByLabelText('When') as HTMLInputElement;
    expect(input.type).toBe(kind);
    fireEvent.change(input, { target: { value } });
    expect(onChange).toHaveBeenCalledWith(value);
    await expectNoAxeViolations(container);
  });

  it('passes limits and errors through', () => {
    render(
      <DateTimePicker
        label="Start"
        name="start"
        kind="date"
        value=""
        min="2026-01-01"
        max="2026-12-31"
        error="Pick a date this year"
        onChange={() => undefined}
      />,
    );
    const input = screen.getByLabelText('Start') as HTMLInputElement;
    expect(input.min).toBe('2026-01-01');
    expect(input.max).toBe('2026-12-31');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    const errorId = screen.getByText('Pick a date this year').id;
    expect(errorId).not.toBe('');
    expect(input.getAttribute('aria-describedby')?.split(' ')).toContain(errorId);
  });
});
