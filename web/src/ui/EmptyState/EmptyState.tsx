import { Button } from '../Button';
import { Icon, type IconName } from '../icons';
import styles from './EmptyState.module.css';

export interface EmptyStateProps {
  title: string;
  body?: string;
  icon?: IconName;
  action?: { label: string; onClick: () => void };
}

/** Spec 5.5; plan 5.5: what a screen shows when there is nothing yet, with an inviting next step. */
export function EmptyState({ title, body, icon = 'info', action }: EmptyStateProps) {
  return (
    <div className={styles.state}>
      <span className={styles.badge}>
        <Icon name={icon} />
      </span>
      <h2>{title}</h2>
      {body !== undefined && <p className={styles.body}>{body}</p>}
      {action !== undefined && (
        <Button variant="secondary" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
