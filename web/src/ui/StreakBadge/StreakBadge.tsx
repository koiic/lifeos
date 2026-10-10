import { copy } from '../../copy/en-GB';
import styles from './StreakBadge.module.css';

export interface StreakBadgeProps {
  days: number;
}

const MILESTONES = new Set([3, 7, 14, 30]);

/**
 * Spec 4.3 TOD-5: "Consecutive days with a daily_log; shown as a Sticker Book badge from 3 days".
 * Spec 5.6: "Streak badge wiggles on day 3, 7, 14, 30. All motion disabled under prefers-reduced-motion".
 */
export function StreakBadge({ days }: StreakBadgeProps) {
  if (days < 3) return null;

  const isMilestone = MILESTONES.has(days);
  const badgeClasses = [styles.badge, isMilestone ? styles.wiggle : ''].filter(Boolean).join(' ');

  return (
    <div
      className={badgeClasses}
      role="status"
      aria-label={copy.today.streakBadgeAria(days)}
      data-testid="streak-badge"
    >
      <span className={styles.flame} aria-hidden="true">
        🔥
      </span>
      <span>{copy.today.streak(days)}</span>
    </div>
  );
}
