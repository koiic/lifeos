import { copy } from '../../copy/en-GB';
import { Icon } from '../../ui/icons';
import styles from './SleepStepper.module.css';

const t = copy.checkin.sleep;

export interface SleepStepperProps {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

const DEFAULT_HOURS = 7.5;
const MIN_HOURS = 0.0;
const MAX_HOURS = 14.0;
const STEP = 0.5;

/** 0–14 sleep hours stepper in 0.5 steps (CHK-1). */
export function SleepStepper({ value, onChange, disabled }: SleepStepperProps) {
  const onDecrease = () => {
    if (value === null) {
      onChange(DEFAULT_HOURS);
    } else {
      const next = Math.max(MIN_HOURS, Math.round((value - STEP) * 2) / 2);
      onChange(next);
    }
  };

  const onIncrease = () => {
    if (value === null) {
      onChange(DEFAULT_HOURS);
    } else {
      const next = Math.min(MAX_HOURS, Math.round((value + STEP) * 2) / 2);
      onChange(next);
    }
  };

  return (
    <div className={styles.wrapper}>
      <span className={styles.label} id="sleep-stepper-label">
        {t.label}
      </span>
      <div className={styles.controls}>
        <button
          type="button"
          aria-label={t.decrease}
          disabled={disabled || (value !== null && value <= MIN_HOURS)}
          className={styles.stepButton}
          onClick={onDecrease}
        >
          <Icon name="minus" size="sm" />
        </button>
        <div
          role="status"
          aria-live="polite"
          aria-labelledby="sleep-stepper-label"
          className={styles.display}
        >
          {value !== null ? t.hours(value) : t.notLogged}
        </div>
        <button
          type="button"
          aria-label={t.increase}
          disabled={disabled || (value !== null && value >= MAX_HOURS)}
          className={styles.stepButton}
          onClick={onIncrease}
        >
          <Icon name="plus" size="sm" />
        </button>
        {value !== null && (
          <button
            type="button"
            className={styles.clearButton}
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            {t.clear}
          </button>
        )}
      </div>
    </div>
  );
}
