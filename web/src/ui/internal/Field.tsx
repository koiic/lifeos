import { type ReactNode, useId } from 'react';

import styles from './Field.module.css';

export interface FieldText {
  label: string;
  hint?: string;
  error?: string;
}

export interface ControlIds {
  id: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
}

/**
 * The label, hint and error around one form control; `children` receives the ids that tie them
 * together (label `for`, `aria-describedby`, `aria-invalid`).
 */
export function Field({
  label,
  hint,
  error,
  children,
}: FieldText & { children: (ids: ControlIds) => ReactNode }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint === undefined ? null : hintId, error === undefined ? null : errorId]
    .filter((value) => value !== null)
    .join(' ');
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      {children({
        id,
        ...(describedBy === '' ? {} : { 'aria-describedby': describedBy }),
        ...(error === undefined ? {} : { 'aria-invalid': true as const }),
      })}
      {hint !== undefined && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
