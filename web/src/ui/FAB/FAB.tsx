import { Icon, type IconName } from '../icons';
import styles from './FAB.module.css';

export interface FABProps {
  /** Accessible name (spec 5.8: icon-only controls have aria-label). */
  label: string;
  icon?: IconName;
  onClick: () => void;
}

/** Spec 5.5: the floating add button, in --sun (5.3: "Add button"). */
export function FAB({ label, icon = 'plus', onClick }: FABProps) {
  return (
    <button type="button" className={styles.fab} aria-label={label} onClick={onClick}>
      <Icon name={icon} />
    </button>
  );
}
