import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Switch } from './Switch';

afterEach(cleanup);

describe('Switch (spec 5.5)', () => {
  it('is a labelled switch that toggles', async () => {
    const onChange = vi.fn();
    const { container, rerender } = render(
      <Switch label="Discreet notifications" checked={false} onChange={onChange} />,
    );
    const toggle = screen.getByRole('switch', { name: 'Discreet notifications' });
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
    rerender(<Switch label="Discreet notifications" checked onChange={onChange} />);
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    await expectNoAxeViolations(container);
  });

  it('is a keyboard-reachable button with an optional description', () => {
    render(
      <Switch
        label="App lock"
        description="Asks after 5 minutes"
        checked
        onChange={() => undefined}
      />,
    );
    const toggle = screen.getByRole('switch', { name: 'App lock' });
    expect(toggle.tagName).toBe('BUTTON');
    toggle.focus();
    expect(document.activeElement).toBe(toggle);
    expect(toggle.getAttribute('aria-describedby')).toBe(
      screen.getByText('Asks after 5 minutes').id,
    );
  });
});
