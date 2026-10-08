import type { ReactNode } from 'react';

import { Icon, type IconName } from '../icons';
import styles from './Button.module.css';

interface Common {
  type?: 'button' | 'submit';
  disabled?: boolean;
  /** Working: announced as busy and not clickable. */
  busy?: boolean;
  onClick?: () => void;
}

interface TextButtonProps extends Common {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  /** Optional leading icon (decorative). */
  icon?: IconName;
  children: ReactNode;
}

interface IconButtonProps extends Common {
  variant: 'icon';
  icon: IconName;
  /** The accessible name of an icon-only button (spec 5.8). */
  label: string;
}

/** A link that looks like a button: for leaving the app (e.g. opening the authenticator app). */
interface LinkButtonProps {
  href: string;
  variant?: 'primary' | 'secondary' | 'ghost';
  icon?: IconName;
  children: ReactNode;
}

export type ButtonProps = TextButtonProps | IconButtonProps | LinkButtonProps;

/**
 * Spec 5.5: primary, secondary, ghost, danger and icon buttons; real `<button>`s (5.8), or a real
 * link when it goes somewhere (`href`).
 */
export function Button(props: ButtonProps) {
  if ('href' in props) {
    return (
      <a className={styles.button} data-variant={props.variant ?? 'primary'} href={props.href}>
        {props.icon !== undefined && <Icon name={props.icon} size="sm" />}
        {props.children}
      </a>
    );
  }
  const { type = 'button', disabled = false, busy = false, onClick } = props;
  const variant = props.variant ?? 'primary';
  return (
    <button
      type={type}
      className={styles.button}
      data-variant={variant}
      // Busy stays focusable (aria-disabled, not disabled) so a keyboard user keeps their place
      // when a submit starts working (WCAG 2.4.3).
      disabled={disabled}
      aria-disabled={busy || undefined}
      aria-busy={busy || undefined}
      aria-label={props.variant === 'icon' ? props.label : undefined}
      onClick={(event) => {
        // Busy is aria-disabled, not disabled, so the browser would still submit a form (by click
        // or Enter in a field); cancelling the click stops both.
        if (busy) {
          event.preventDefault();
          return;
        }
        onClick?.();
      }}
    >
      {/* Busy shows a still clock (nothing loops, spec 5.6), so it reads differently from disabled. */}
      {(busy || props.icon !== undefined) && (
        <Icon
          name={busy ? 'clock' : (props.icon ?? 'clock')}
          size={props.variant === 'icon' ? 'md' : 'sm'}
        />
      )}
      {props.variant !== 'icon' && props.children}
    </button>
  );
}
