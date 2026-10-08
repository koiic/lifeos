import { type FormEvent, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { Button } from '../Button';
import { Icon } from '../icons';
import { useFocusTrap } from '../internal/useFocusTrap';
import { TextField } from '../TextField';
import styles from './LockScreen.module.css';

export interface LockScreenProps {
  title: string;
  /** Unlock with a passkey (user verification). Absent when she has no passkey. */
  passkey?: { label: string; onUnlock: () => void; busy?: boolean };
  /** Unlock with her 6-digit PIN. */
  pin?: {
    label: string;
    submitLabel: string;
    /** Called only with exactly 6 digits (each wrong PIN uses up one of her tries, CR-021). */
    onSubmit: (pin: string) => void;
    /** Shown when what she typed is not 6 digits. */
    invalidMessage: string;
    error?: string;
    busy?: boolean;
  };
  signOut?: { label: string; onClick: () => void };
}

const noop = () => undefined;

/**
 * Spec 5.5, 11.6: the app lock, over everything (dialogs and sheets included). With only a
 * title it is the cover shown while the app is in the background. It cannot be dismissed.
 */
export function LockScreen({ title, passkey, pin, signOut }: LockScreenProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const onKeyDown = useFocusTrap(panel, true, noop);
  const [value, setValue] = useState('');
  const [invalid, setInvalid] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pin === undefined || pin.busy === true) return;
    if (!/^\d{6}$/.test(value)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    pin.onSubmit(value);
    setValue('');
  };
  const pinError = invalid ? pin?.invalidMessage : pin?.error;

  return createPortal(
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- a modal dialog handles Tab for its focus trap (WAI-ARIA dialog pattern)
    <div
      ref={panel}
      className={styles.screen}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      onKeyDown={onKeyDown}
    >
      <div className={styles.panel}>
        <span className={styles.badge}>
          <Icon name="lock" />
        </span>
        <h1 id={titleId} className={styles.title}>
          {title}
        </h1>
        {passkey !== undefined && (
          <Button icon="key" busy={passkey.busy ?? false} onClick={passkey.onUnlock}>
            {passkey.label}
          </Button>
        )}
        {pin !== undefined && (
          <form className={styles.pin} onSubmit={submit} noValidate>
            <TextField
              label={pin.label}
              name="pin"
              type="password"
              inputMode="numeric"
              maxLength={6}
              autoComplete="off"
              value={value}
              onChange={setValue}
              {...(pinError === undefined ? {} : { error: pinError })}
            />
            <Button type="submit" variant="secondary" busy={pin.busy ?? false}>
              {pin.submitLabel}
            </Button>
          </form>
        )}
        {signOut !== undefined && (
          <Button variant="ghost" onClick={signOut.onClick}>
            {signOut.label}
          </Button>
        )}
      </div>
    </div>,
    document.body,
  );
}
