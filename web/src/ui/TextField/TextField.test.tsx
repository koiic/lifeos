import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { TextField } from './TextField';

afterEach(cleanup);

describe('TextField (spec 5.5)', () => {
  it('is a labelled input that reports changes', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <TextField label="Email" name="email" type="email" value="" onChange={onChange} />,
    );
    const input = screen.getByRole('textbox', { name: 'Email' }) as HTMLInputElement;
    expect(input.type).toBe('email');
    fireEvent.change(input, { target: { value: 'z@example.test' } });
    expect(onChange).toHaveBeenCalledWith('z@example.test');
    await expectNoAxeViolations(container);
  });

  it('a hint describes the input', () => {
    render(
      <TextField
        label="Name"
        name="name"
        value=""
        hint="As you'd like to be called"
        onChange={() => undefined}
      />,
    );
    const input = screen.getByRole('textbox', { name: 'Name' });
    const hint = screen.getByText("As you'd like to be called");
    expect(input.getAttribute('aria-describedby')).toContain(hint.id);
    expect(input.getAttribute('aria-invalid')).toBeNull();
  });

  it('an error marks the input invalid and describes it', async () => {
    const { container } = render(
      <TextField
        label="Name"
        name="name"
        value=""
        error="Enter your name"
        required
        onChange={() => undefined}
      />,
    );
    const input = screen.getByRole('textbox', { name: 'Name' });
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.hasAttribute('required')).toBe(true);
    expect(input.getAttribute('aria-describedby')).toContain(
      screen.getByText('Enter your name').id,
    );
    await expectNoAxeViolations(container);
  });
});
