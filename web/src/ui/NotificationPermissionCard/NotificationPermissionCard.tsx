import { useId } from 'react';

import { Button } from '../Button';
import { Card } from '../Card';
import { Icon, type IconName } from '../icons';
import styles from './NotificationPermissionCard.module.css';

export type NotificationPermissionState =
  'prompt' | 'granted' | 'denied' | 'needs-install' | 'unsupported';

type Action =
  { label: string; onClick: () => void; busy?: boolean } | { label: string; href: string };

export interface NotificationPermissionCardProps {
  state: NotificationPermissionState;
  title: string;
  body: string;
  /** The one thing she can do here: turn on, send a test, or go to the install guide. */
  action?: Action;
  /** Denied: the numbered steps to allow notifications again (ONB-3). */
  steps?: { label: string; items: readonly string[] };
  /** The outcome of the last action, announced politely. */
  status?: string;
}

const ICONS: Record<NotificationPermissionState, IconName> = {
  prompt: 'clock',
  granted: 'check',
  denied: 'alert',
  'needs-install': 'addToHome',
  unsupported: 'info',
};

/** Spec 5.5, ONB-3, 10.6: where notifications stand on this device and what to do next. */
export function NotificationPermissionCard({
  state,
  title,
  body,
  action,
  steps,
  status,
}: NotificationPermissionCardProps) {
  const id = useId();
  return (
    <Card as="section" labelledBy={id}>
      <span className={styles.badge} data-state={state}>
        <Icon name={ICONS[state]} />
      </span>
      <h2 id={id}>{title}</h2>
      <p>{body}</p>
      {steps !== undefined && (
        <ol className={styles.steps} aria-label={steps.label}>
          {steps.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      )}
      {action !== undefined &&
        ('href' in action ? (
          <Button href={action.href}>{action.label}</Button>
        ) : (
          <Button busy={action.busy ?? false} onClick={action.onClick}>
            {action.label}
          </Button>
        ))}
      <p className={styles.status} role="status">
        {status ?? ''}
      </p>
    </Card>
  );
}
