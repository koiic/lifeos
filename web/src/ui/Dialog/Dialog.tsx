import { type ReactNode, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

import { useFocusTrap } from '../internal/useFocusTrap';
import styles from './Dialog.module.css';

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  /** A confirmation that interrupts (e.g. deleting): role alertdialog. */
  alert?: boolean;
  onClose: () => void;
  /** The dialog's buttons. */
  actions: ReactNode;
  children?: ReactNode;
}

/** Spec 5.5: a centred dialog with a focus trap; Escape closes; focus returns (5.8). */
export function Dialog({
  open,
  title,
  description,
  alert = false,
  onClose,
  actions,
  children,
}: DialogProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const onKeyDown = useFocusTrap(panel, open, onClose);
  if (!open) return null;
  return createPortal(
    <div className={styles.layer}>
      {/* A confirmation is not dismissed by a stray tap: only its buttons or Escape close it. */}
      <div
        className={styles.scrim}
        data-scrim
        aria-hidden="true"
        onClick={alert ? undefined : onClose}
      />
      <div
        ref={panel}
        className={styles.dialog}
        role={alert ? 'alertdialog' : 'dialog'}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId}>{title}</h2>
        {description !== undefined && (
          <p id={descriptionId} className={styles.description}>
            {description}
          </p>
        )}
        {children}
        <div className={styles.actions}>{actions}</div>
      </div>
    </div>,
    document.body,
  );
}
