import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { LockScreen } from './LockScreen';

afterEach(cleanup);

function full(overrides: Partial<Parameters<typeof LockScreen>[0]> = {}) {
  const props = {
    title: 'Life OS is locked',
    passkey: { label: 'Unlock with passkey', onUnlock: vi.fn() },
    pin: {
      label: 'PIN',
      submitLabel: 'Unlock',
      onSubmit: vi.fn(),
      invalidMessage: 'Enter your 6-digit PIN',
    },
    signOut: { label: 'Sign out', onClick: vi.fn() },
    ...overrides,
  };
  return { props, ...render(<LockScreen {...props} />) };
}

describe('[AUTH-6] LockScreen (spec 5.5, 11.6)', () => {
  it('is a labelled modal over the whole app, with focus inside', async () => {
    const { baseElement } = full();
    const dialog = screen.getByRole('dialog', { name: 'Life OS is locked' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.contains(document.activeElement)).toBe(true);
    await expectNoAxeViolations(baseElement);
  });

  it('unlocks with a passkey', () => {
    const { props } = full();
    fireEvent.click(screen.getByRole('button', { name: 'Unlock with passkey' }));
    expect(props.passkey.onUnlock).toHaveBeenCalledOnce();
  });

  it('unlocks with a 6-digit PIN typed on the number pad', () => {
    const { props } = full();
    const pin = screen.getByLabelText('PIN') as HTMLInputElement;
    expect(pin.inputMode).toBe('numeric');
    expect(pin.maxLength).toBe(6);
    expect(pin.autocomplete).toBe('off');
    fireEvent.change(pin, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
    expect(props.pin.onSubmit).toHaveBeenCalledWith('123456');
    expect(pin.value).toBe('');
  });

  it('shows a PIN error tied to the field', () => {
    full({
      pin: {
        label: 'PIN',
        submitLabel: 'Unlock',
        onSubmit: vi.fn(),
        invalidMessage: 'Enter your 6-digit PIN',
        error: 'Wrong PIN',
      },
    });
    const pin = screen.getByLabelText('PIN');
    expect(pin.getAttribute('aria-invalid')).toBe('true');
    expect(pin.getAttribute('aria-describedby')?.split(' ')).toContain(
      screen.getByText('Wrong PIN').id,
    );
  });

  it('Escape does not dismiss it', () => {
    const { props } = full();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeDefined();
    expect(props.signOut.onClick).not.toHaveBeenCalled();
  });

  it('offers signing out instead', () => {
    const { props } = full();
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(props.signOut.onClick).toHaveBeenCalledOnce();
  });

  it('the cover shown while the app is in the background has the title only', async () => {
    const { baseElement } = render(<LockScreen title="Life OS is locked" />);
    expect(screen.getByRole('dialog', { name: 'Life OS is locked' })).toBeDefined();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByRole('textbox')).toBeNull();
    await expectNoAxeViolations(baseElement);
  });

  it('a busy unlock cannot be pressed twice', () => {
    const onUnlock = vi.fn();
    full({ passkey: { label: 'Unlock with passkey', onUnlock, busy: true } });
    fireEvent.click(screen.getByRole('button', { name: 'Unlock with passkey' }));
    expect(onUnlock).not.toHaveBeenCalled();
  });

  it('a PIN that is not 6 digits is not sent (it would use up one of her tries)', () => {
    const onSubmit = vi.fn();
    render(
      <LockScreen
        title="Life OS is locked"
        pin={{
          label: 'PIN',
          submitLabel: 'Unlock',
          onSubmit,
          invalidMessage: 'Enter your 6-digit PIN',
        }}
      />,
    );
    for (const typed of ['12345', '1234567']) {
      // maxLength limits typing only; a paste or autofill can still bring 7 digits.
      fireEvent.change(screen.getByLabelText('PIN'), { target: { value: typed } });
      fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
    }
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Enter your 6-digit PIN')).toBeDefined();
    expect(screen.getByLabelText('PIN').getAttribute('aria-invalid')).toBe('true');
  });
});
