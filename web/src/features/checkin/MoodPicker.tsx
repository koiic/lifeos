import { copy } from '../../copy/en-GB';
import styles from './MoodPicker.module.css';

const t = copy.checkin.mood;

export interface MoodOption {
  value: number;
  label: string;
  emoji: string;
}

export const MOODS: readonly MoodOption[] = [
  { value: 5, label: t.bright, emoji: '☀️' },
  { value: 4, label: t.good, emoji: '😊' },
  { value: 3, label: t.okay, emoji: '😐' },
  { value: 2, label: t.tired, emoji: '🥱' },
  { value: 1, label: t.low, emoji: '🌧️' },
] as const;

export interface MoodPickerProps {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

/** 5-point mood picker (CHK-1): Bright, Good, Okay, Tired, Low. */
export function MoodPicker({ value, onChange, disabled }: MoodPickerProps) {
  return (
    <div className={styles.wrapper}>
      <span className={styles.label} id="mood-picker-label">
        {t.label}
      </span>
      <div role="radiogroup" aria-labelledby="mood-picker-label" className={styles.group}>
        {MOODS.map((m) => {
          const selected = value === m.value;
          return (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              className={styles.button}
              data-selected={selected}
              onClick={() => onChange(selected ? null : m.value)}
            >
              <span className={styles.emoji} aria-hidden="true">
                {m.emoji}
              </span>
              <span className={styles.text}>{m.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
