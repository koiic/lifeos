import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Sheet } from './Sheet';

afterEach(cleanup);

function Harness({ onClose = () => undefined }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Sheet
        open={open}
        title="Check-in"
        closeLabel="Close"
        onClose={() => {
          onClose();
          setOpen(false);
        }}
      >
        <label htmlFor="mood">Mood</label>
        <input id="mood" />
        <button type="button">Save</button>
      </Sheet>
    </>
  );
}

describe('Sheet (spec 5.5: bottom sheet with drag handle and focus trap; 5.8)', () => {
  it('is closed until opened', () => {
    render(<Harness />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens as a labelled modal dialog and moves focus inside', async () => {
    const { baseElement } = render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const dialog = screen.getByRole('dialog', { name: 'Check-in' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.contains(document.activeElement)).toBe(true);
    await expectNoAxeViolations(baseElement);
  });

  it('traps Tab and Shift+Tab inside', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const close = screen.getByRole('button', { name: 'Close' });
    const save = screen.getByRole('button', { name: 'Save' });
    save.focus();
    fireEvent.keyDown(save, { key: 'Tab' });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(save);
  });

  it('closes on Escape and on the close button, returning focus to the opener', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole('button', { name: 'Open' });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
    fireEvent.click(opener);
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(opener);
  });

  it('shows a drag handle that assistive technology skips (the close button is the alternative)', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const handle = screen.getByRole('dialog').querySelector('[data-handle]');
    expect(handle?.getAttribute('aria-hidden')).toBe('true');
  });

  it('dragging the handle down far enough closes it and returns focus', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole('button', { name: 'Open' });
    opener.focus();
    fireEvent.click(opener);
    const grip = screen.getByRole('dialog').querySelector('[data-grip]') as Element;
    fireEvent.pointerDown(grip, { clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(grip, { clientY: 200, pointerId: 1 });
    fireEvent.pointerUp(grip, { clientY: 200, pointerId: 1 });
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it('a short drag snaps back and keeps it open', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const dialog = screen.getByRole('dialog');
    const grip = dialog.querySelector('[data-grip]') as Element;
    fireEvent.pointerDown(grip, { clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(grip, { clientY: 120, pointerId: 1 });
    expect(dialog.style.transform).toBe('translateY(20px)');
    expect(dialog.dataset.dragging).toBe('true');
    fireEvent.pointerUp(grip, { clientY: 120, pointerId: 1 });
    expect(onClose).not.toHaveBeenCalled();
    expect(dialog.style.transform).toBe('');
    expect(dialog.dataset.dragging).toBeUndefined();
  });

  it('a pointer that only moves (no press) does nothing', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const dialog = screen.getByRole('dialog');
    const grip = dialog.querySelector('[data-grip]') as Element;
    fireEvent.pointerMove(grip, { clientY: 400, pointerId: 1 });
    fireEvent.pointerUp(grip, { clientY: 400, pointerId: 1 });
    expect(dialog.style.transform).toBe('');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('a tap on the scrim closes it and returns focus to the opener', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole('button', { name: 'Open' });
    opener.focus();
    fireEvent.click(opener);
    const scrim = document.querySelector('[data-scrim]');
    expect(scrim).not.toBeNull();
    fireEvent.click(scrim as Element);
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it('a press that starts on the close button is a click, not a drag', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    const dialog = screen.getByRole('dialog');
    const close = screen.getByRole('button', { name: 'Close' });
    fireEvent.pointerDown(close, { clientY: 100, pointerId: 1 });
    expect(dialog.dataset.dragging).toBeUndefined();
    fireEvent.pointerMove(close, { clientY: 300, pointerId: 1 });
    expect(dialog.style.transform).toBe('');
  });
});
