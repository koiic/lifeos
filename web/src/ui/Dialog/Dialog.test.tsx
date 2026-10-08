import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Button } from '../Button';
import { expectNoAxeViolations } from '../testing/axe';
import { Dialog } from './Dialog';

afterEach(cleanup);

function Harness({
  alert = false,
  onClose = () => undefined,
}: {
  alert?: boolean;
  onClose?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const close = () => {
    onClose();
    setOpen(false);
  };
  return (
    <>
      <Button onClick={() => setOpen(true)}>Delete</Button>
      <Dialog
        open={open}
        alert={alert}
        title="Delete this note?"
        description="You can't undo this."
        onClose={close}
        actions={
          <>
            <Button variant="secondary" onClick={close}>
              Keep
            </Button>
            <Button variant="danger" onClick={close}>
              Delete note
            </Button>
          </>
        }
      />
    </>
  );
}

describe('Dialog (spec 5.5; 5.8 focus trap and return)', () => {
  it('opens labelled and described, with focus inside', async () => {
    const { baseElement } = render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const dialog = screen.getByRole('dialog', { name: 'Delete this note?' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy();
    expect(screen.getByText("You can't undo this.").id).toBe(
      dialog.getAttribute('aria-describedby'),
    );
    expect(dialog.contains(document.activeElement)).toBe(true);
    await expectNoAxeViolations(baseElement);
  });

  it('a confirmation is an alertdialog', () => {
    render(<Harness alert />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(screen.getByRole('alertdialog', { name: 'Delete this note?' })).toBeDefined();
  });

  it('traps focus, closes on Escape and returns focus', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole('button', { name: 'Delete' });
    opener.focus();
    fireEvent.click(opener);
    const keep = screen.getByRole('button', { name: 'Keep' });
    const confirm = screen.getByRole('button', { name: 'Delete note' });
    confirm.focus();
    fireEvent.keyDown(confirm, { key: 'Tab' });
    expect(document.activeElement).toBe(keep);
    fireEvent.keyDown(keep, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it('Shift+Tab from the first control wraps to the last', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const keep = screen.getByRole('button', { name: 'Keep' });
    expect(document.activeElement).toBe(keep);
    fireEvent.keyDown(keep, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Delete note' }));
  });

  it('a tap on the scrim closes a plain dialog and returns focus', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole('button', { name: 'Delete' });
    opener.focus();
    fireEvent.click(opener);
    const scrim = document.querySelector('[data-scrim]');
    expect(scrim).not.toBeNull();
    fireEvent.click(scrim as Element);
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it('a confirmation (alert) is not dismissed by a stray tap on the scrim', () => {
    const onClose = vi.fn();
    render(<Harness alert onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(document.querySelector('[data-scrim]') as Element);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toBeDefined();
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('with no focusable content, focus goes to the dialog itself and Tab stays there', () => {
    render(
      <Dialog open title="Saved" onClose={() => undefined} actions={<span>Nothing to do</span>} />,
    );
    const dialog = screen.getByRole('dialog', { name: 'Saved' });
    expect(document.activeElement).toBe(dialog);
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(dialog);
  });
});
