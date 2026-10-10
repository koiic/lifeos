import { copy } from '../../copy/en-GB';
import styles from './EnergySlider.module.css';

const t = copy.checkin.energy;

export interface EnergySliderProps {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

const LEVELS = [1, 2, 3, 4, 5] as const;

/** 1–5 energy level picker (CHK-1). */
export function EnergySlider({ value, onChange, disabled }: EnergySliderProps) {
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.label} id="energy-slider-label">
          {t.label}
        </span>
        {value !== null && <span className={styles.value}>{t.outOfFive(value)}</span>}
      </div>
      <div role="radiogroup" aria-labelledby="energy-slider-label" className={styles.group}>
        {LEVELS.map((level) => {
          const selected = value === level;
          const accessibleName = t.levelLabel(level);
          return (
            <button
              key={level}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={accessibleName}
              disabled={disabled}
              className={styles.button}
              data-selected={selected}
              onClick={() => onChange(selected ? null : level)}
            >
              {t.levelText(level)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
