import { NavLink } from 'react-router-dom';

import { Icon, type IconName } from '../icons';
import styles from './BottomNav.module.css';

export interface BottomNavItem {
  to: string;
  label: string;
  icon: IconName;
}

/** The centre "+" slot: a button, not a route (it opens the quick-add sheet, TOD-6). */
export interface BottomNavAction {
  label: string;
  onPress: () => void;
}

export interface BottomNavProps {
  /** Names the navigation landmark. */
  label: string;
  items: readonly BottomNavItem[];
  action: BottomNavAction;
}

/**
 * Spec 5.1, 5.5: the tab bar; the current tab is marked aria-current="page". The action sits in
 * the middle slot (Today, Health, +, Calendar, More).
 */
export function BottomNav({ label, items, action }: BottomNavProps) {
  const middle = Math.ceil(items.length / 2);
  const link = (item: BottomNavItem) => (
    <li key={item.to} className={styles.item}>
      <NavLink to={item.to} className={styles.link ?? ''}>
        <Icon name={item.icon} />
        <span className={styles.label}>{item.label}</span>
      </NavLink>
    </li>
  );
  return (
    <nav className={styles.nav} aria-label={label}>
      <ul className={styles.list}>
        {items.slice(0, middle).map(link)}
        <li className={styles.item}>
          <button
            type="button"
            className={styles.action}
            aria-label={action.label}
            onClick={action.onPress}
          >
            <Icon name="plus" />
          </button>
        </li>
        {items.slice(middle).map(link)}
      </ul>
    </nav>
  );
}
