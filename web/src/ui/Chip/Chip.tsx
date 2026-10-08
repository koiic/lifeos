import type { ReactNode } from 'react';

import { Icon, type IconName } from '../icons';
import hidden from '../internal/visuallyHidden.module.css';
import styles from './Chip.module.css';

export interface ChipProps {
  pressed: boolean;
  onChange: (pressed: boolean) => void;
  icon?: IconName;
  children: ReactNode;
}

/** Spec 5.5 toggle chip: a button that is pressed or not (e.g. one symptom). */
export function Chip({ pressed, onChange, icon, children }: ChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      aria-pressed={pressed}
      onClick={() => onChange(!pressed)}
    >
      {/* Spec 5.8: the state is never shown by colour alone. */}
      {pressed ? (
        <Icon name="check" size="sm" />
      ) : (
        icon !== undefined && <Icon name={icon} size="sm" />
      )}
      {children}
    </button>
  );
}

export interface ChipOption<V extends string> {
  value: V;
  label: string;
}

export interface ChipGroupProps<V extends string> {
  legend: string;
  name: string;
  options: readonly ChipOption<V>[];
  value: V | null;
  onChange: (value: V) => void;
}

/** Spec 5.5 choice chips: one value from a labelled radio group (arrow keys move between them). */
export function ChipGroup<V extends string>({
  legend,
  name,
  options,
  value,
  onChange,
}: ChipGroupProps<V>) {
  return (
    <fieldset className={styles.group} role="radiogroup">
      <legend className={styles.legend}>{legend}</legend>
      <div className={styles.options}>
        {options.map((option) => (
          <label key={option.value} className={styles.choice}>
            <input
              className={`${hidden.visuallyHidden} ${styles.input}`}
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span className={styles.chip}>
              {value === option.value && <Icon name="check" size="sm" />}
              {option.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
