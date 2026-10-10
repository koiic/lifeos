import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MoodPicker } from './MoodPicker';

afterEach(cleanup);

describe('MoodPicker', () => {
  it('renders all 5 moods with radio roles', () => {
    render(<MoodPicker value={null} onChange={() => {}} />);
    const group = screen.getByRole('radiogroup', { name: 'Mood' });
    expect(group).toBeDefined();

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(5);
    expect(screen.getByRole('radio', { name: /bright/i })).toBeDefined();
    expect(screen.getByRole('radio', { name: /good/i })).toBeDefined();
    expect(screen.getByRole('radio', { name: /okay/i })).toBeDefined();
    expect(screen.getByRole('radio', { name: /tired/i })).toBeDefined();
    expect(screen.getByRole('radio', { name: /low/i })).toBeDefined();
  });

  it('indicates checked state and calls onChange when tapped', () => {
    const onChange = vi.fn();
    const { rerender } = render(<MoodPicker value={4} onChange={onChange} />);

    const good = screen.getByRole('radio', { name: /good/i });
    expect(good.getAttribute('aria-checked')).toBe('true');

    const bright = screen.getByRole('radio', { name: /bright/i });
    expect(bright.getAttribute('aria-checked')).toBe('false');

    fireEvent.click(bright);
    expect(onChange).toHaveBeenCalledWith(5);

    // Clicking already selected toggles it off
    rerender(<MoodPicker value={5} onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: /bright/i }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
