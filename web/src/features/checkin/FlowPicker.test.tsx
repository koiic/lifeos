import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FlowPicker } from './FlowPicker';

afterEach(cleanup);

describe('FlowPicker', () => {
  it('renders all 5 flow choices', () => {
    render(<FlowPicker value="none" onChange={() => {}} />);
    const group = screen.getByRole('radiogroup', { name: 'Flow' });
    expect(group).toBeDefined();

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(5);
    expect(screen.getByRole('radio', { name: 'None' })).toBeDefined();
    expect(screen.getByRole('radio', { name: 'Medium' })).toBeDefined();
  });

  it('selects flow option on click', () => {
    const onChange = vi.fn();
    render(<FlowPicker value="none" onChange={onChange} />);

    const medium = screen.getByRole('radio', { name: 'Medium' });
    fireEvent.click(medium);
    expect(onChange).toHaveBeenCalledWith('medium');
  });
});
