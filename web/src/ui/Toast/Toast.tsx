import { Button } from '../Button';
import { Icon } from '../icons';
import styles from './Toast.module.css';

export interface ToastProps {
  message: string;
  tone?: 'info' | 'success' | 'danger';
  action?: { label: string; onClick: () => void };
  dismissLabel: string;
  onDismiss: () => void;
}

/** Spec 5.5: a short message; errors are announced as alerts, the rest politely. */
export function Toast({ message, tone = 'info', action, dismissLabel, onDismiss }: ToastProps) {
  return (
    <div className={styles.toast} data-tone={tone} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon name={tone === 'danger' ? 'alert' : tone === 'success' ? 'check' : 'info'} size="sm" />
      <p className={styles.message}>{message}</p>
      {action !== undefined && (
        <Button variant="ghost" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      <Button variant="icon" icon="close" label={dismissLabel} onClick={onDismiss} />
    </div>
  );
}
