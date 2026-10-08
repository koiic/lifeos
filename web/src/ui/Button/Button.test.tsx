import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Button } from './Button';

afterEach(cleanup);

describe('Button (spec 5.5: primary, secondary, ghost, danger, icon)', () => {
  it.each(['primary', 'secondary', 'ghost', 'danger'] as const)(
    '%s is a real button that clicks',
    async (variant) => {
      const onClick = vi.fn();
      const { container } = render(
        <Button variant={variant} onClick={onClick}>
          Save
        </Button>,
      );
      const button = screen.getByRole('button', { name: 'Save' });
      expect(button.getAttribute('type')).toBe('button');
      expect(button.dataset.variant).toBe(variant);
      fireEvent.click(button);
      expect(onClick).toHaveBeenCalledOnce();
      await expectNoAxeViolations(container);
    },
  );

  it('is reachable by keyboard', () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    button.focus();
    expect(document.activeElement).toBe(button);
    expect(button.tabIndex).toBe(0);
  });

  it('can submit a form', () => {
    const onSubmit = vi.fn((event: { preventDefault(): void }) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button type="submit">Send</Button>
      </form>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('a disabled or busy button does not click', () => {
    const onClick = vi.fn();
    render(
      <>
        <Button disabled onClick={onClick}>
          Off
        </Button>
        <Button busy onClick={onClick}>
          Saving
        </Button>
      </>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Off' }));
    const busy = screen.getByRole('button', { name: 'Saving' });
    fireEvent.click(busy);
    expect(onClick).not.toHaveBeenCalled();
    expect(busy.getAttribute('aria-busy')).toBe('true');
  });

  it('a busy button looks different from a disabled one: a static clock in place of its icon', () => {
    render(
      <>
        <Button disabled icon="check">
          Off
        </Button>
        <Button busy icon="check">
          Saving
        </Button>
      </>,
    );
    const icon = (name: string) =>
      screen.getByRole('button', { name }).querySelector('svg path')?.getAttribute('d');
    expect(icon('Saving')).not.toBe(icon('Off'));
    expect(screen.getByRole('button', { name: 'Saving' }).querySelectorAll('svg')).toHaveLength(1);
  });

  it('an icon button is named by its label; the icon is decorative', async () => {
    const onClick = vi.fn();
    const { container } = render(
      <Button variant="icon" icon="close" label="Close" onClick={onClick} />,
    );
    const button = screen.getByRole('button', { name: 'Close' });
    expect(button.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    expect(button.textContent).toBe('');
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
    await expectNoAxeViolations(container);
  });

  it('a text button can lead with an icon', () => {
    render(<Button icon="plus">Add</Button>);
    const button = screen.getByRole('button', { name: 'Add' });
    expect(button.querySelector('svg')).not.toBeNull();
  });

  it('accepts no className or style from features (plan 5.3 rule 6)', () => {
    // @ts-expect-error className is not a prop
    render(<Button className="x">A</Button>);
    // @ts-expect-error style is not a prop
    render(<Button style={{}}>B</Button>);
    expect(screen.getByRole('button', { name: 'A' }).classList.contains('x')).toBe(false);
    expect(screen.getByRole('button', { name: 'B' }).getAttribute('style')).toBeNull();
  });

  it('a focused button keeps focus when it becomes busy, and stays unclickable (WCAG 2.4.3)', () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    button.focus();
    rerender(
      <Button busy onClick={onClick}>
        Save
      </Button>,
    );
    expect(document.activeElement).toBe(button);
    expect(button.hasAttribute('disabled')).toBe(false);
    expect(button.getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('a busy submit button does not submit its form', () => {
    const onSubmit = vi.fn((event: { preventDefault: () => void }) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button type="submit" busy>
          Saving
        </Button>
      </form>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Saving' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
