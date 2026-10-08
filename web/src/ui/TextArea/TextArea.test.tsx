import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { TextArea } from './TextArea';

afterEach(cleanup);

describe('TextArea (spec 5.5)', () => {
  it('is a labelled multi-line field', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <TextArea
        label="Note"
        name="note"
        value=""
        rows={4}
        hint="Only you can see this"
        onChange={onChange}
      />,
    );
    const area = screen.getByRole('textbox', { name: 'Note' }) as HTMLTextAreaElement;
    expect(area.tagName).toBe('TEXTAREA');
    expect(area.rows).toBe(4);
    expect(area.getAttribute('aria-describedby')).toContain(
      screen.getByText('Only you can see this').id,
    );
    fireEvent.change(area, { target: { value: 'tired' } });
    expect(onChange).toHaveBeenCalledWith('tired');
    await expectNoAxeViolations(container);
  });

  it('shows an error', () => {
    render(
      <TextArea label="Note" name="note" value="" error="Too long" onChange={() => undefined} />,
    );
    expect(screen.getByRole('textbox', { name: 'Note' }).getAttribute('aria-invalid')).toBe('true');
  });
});
