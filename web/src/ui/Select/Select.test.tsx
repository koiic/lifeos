import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Select } from './Select';

afterEach(cleanup);

const options = [
  { value: 'system', label: 'Match device' },
  { value: 'light', label: 'Sorbet' },
  { value: 'dark', label: 'Night Garden' },
];

describe('Select (spec 5.5)', () => {
  it('is a labelled native select', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <Select label="Theme" name="theme" options={options} value="system" onChange={onChange} />,
    );
    const select = screen.getByRole('combobox', { name: 'Theme' }) as HTMLSelectElement;
    expect(select.value).toBe('system');
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Match device',
      'Sorbet',
      'Night Garden',
    ]);
    fireEvent.change(select, { target: { value: 'dark' } });
    expect(onChange).toHaveBeenCalledWith('dark');
    await expectNoAxeViolations(container);
  });

  it('shows a hint and an error', () => {
    render(
      <Select
        label="Theme"
        name="theme"
        options={options}
        value="system"
        hint="Applies now"
        error="Pick one"
        onChange={() => undefined}
      />,
    );
    const select = screen.getByRole('combobox', { name: 'Theme' });
    expect(select.getAttribute('aria-invalid')).toBe('true');
    expect(select.getAttribute('aria-describedby')).toContain(screen.getByText('Applies now').id);
  });
});
