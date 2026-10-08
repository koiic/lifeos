import { type PointerEvent, type ReactNode, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

import { Button } from '../Button';
import { useFocusTrap } from '../internal/useFocusTrap';
import { dragOffset, shouldClose } from './drag';
import styles from './Sheet.module.css';

export interface SheetProps {
  open: boolean;
  title: string;
  /** Accessible name of the close button. */
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * Spec 5.5: bottom sheet with a drag handle and a focus trap; focus returns on close (5.8).
 * Dragging the handle strip down far enough closes it (CR-024); the close button, the scrim and
 * Escape are the non-drag ways to close (WCAG 2.5.7).
 */
export function Sheet({ open, title, closeLabel, onClose, children }: SheetProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const onKeyDown = useFocusTrap(panel, open, onClose);
  const dragStart = useRef<number | null>(null);

  // The sheet follows the pointer through its own style while dragging (a runtime position, not a
  // design value); letting go either closes it or snaps it back.
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    // A press on a control in the strip (the close button) is a click: capturing the pointer
    // would send the click to the strip instead.
    if (event.target instanceof Element && event.target.closest('button, a, input, select')) return;
    dragStart.current = event.clientY;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    if (panel.current !== null) panel.current.dataset.dragging = 'true';
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStart.current === null || panel.current === null) return;
    panel.current.style.transform = `translateY(${dragOffset(dragStart.current, event.clientY)}px)`;
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragStart.current;
    const node = panel.current;
    dragStart.current = null;
    if (start === null || node === null) return;
    delete node.dataset.dragging;
    node.style.transform = '';
    if (shouldClose(dragOffset(start, event.clientY), node.getBoundingClientRect().height)) {
      onClose();
    }
  };

  if (!open) return null;
  return createPortal(
    <div className={styles.layer}>
      <div className={styles.scrim} data-scrim aria-hidden="true" onClick={onClose} />
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- a modal dialog handles Escape and Tab for its focus trap (WAI-ARIA dialog pattern) */}
      <div
        ref={panel}
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <div
          className={styles.grip}
          data-grip
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <div className={styles.handle} data-handle aria-hidden="true" />
          <div className={styles.header}>
            <h2 id={titleId}>{title}</h2>
            <Button variant="icon" icon="close" label={closeLabel} onClick={onClose} />
          </div>
        </div>
        <div className={styles.body}>{children}</div>
      </div>
    </div>,
    document.body,
  );
}
