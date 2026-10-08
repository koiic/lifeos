import { Button } from '../Button';
import { Icon } from '../icons';
import styles from './ErrorState.module.css';

export interface ErrorStateProps {
  title: string;
  body?: string;
  retry?: { label: string; onClick: () => void };
}

/** Spec 5.5; plan 5.5: what a screen shows when loading failed, with a way to try again. */
export function ErrorState({ title, body, retry }: ErrorStateProps) {
  return (
    <div className={styles.state}>
      <span className={styles.badge} data-tone="danger">
        <Icon name="alert" />
      </span>
      <h2>{title}</h2>
      {body !== undefined && <p className={styles.body}>{body}</p>}
      {retry !== undefined && <Button onClick={retry.onClick}>{retry.label}</Button>}
    </div>
  );
}
