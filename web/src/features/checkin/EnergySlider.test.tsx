import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EnergySlider } from './EnergySlider';

afterEach(cleanup);

describe('EnergySlider', () => {
  it('renders 5 radio options for energy levels', () => {
    render(<EnergySlider value={null} onChange={() => {}} />);
    const group = screen.getByRole('radiogroup', { name: 'Energy' });
    expect(group).toBeDefined();

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(5);
  });

  it('selects and deselects energy level', () => {
    const onChange = vi.fn();
    const { rerender } = render(<EnergySlider value={3} onChange={onChange} />);

    const r3 = screen.getByRole('radio', { name: '3' });
    expect(r3.getAttribute('aria-checked')).toBe('true');

    const r5 = screen.getByRole('radio', { name: /5 - High/i });
    fireEvent.click(r5);
    expect(onChange).toHaveBeenCalledWith(5);

    rerender(<EnergySlider value={5} onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: /5 - High/i }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
