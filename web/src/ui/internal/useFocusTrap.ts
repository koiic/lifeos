import { type KeyboardEvent, type RefObject, useEffect } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(panel: HTMLElement): HTMLElement[] {
  return Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
}

/**
 * Spec 5.8: "sheets trap focus and return it on close". While `open`, focus moves into `panel`;
 * when it closes, focus returns to whatever had it before. Returns the panel's keydown handler
 * (Tab and Shift+Tab cycle inside; Escape calls `onClose`).
 */
export function useFocusTrap(
  panel: RefObject<HTMLElement | null>,
  open: boolean,
  onClose: () => void,
): (event: KeyboardEvent<HTMLElement>) => void {
  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const node = panel.current;
    if (node !== null) (focusables(node)[0] ?? node).focus();
    return () => previous?.focus();
  }, [open, panel]);

  return (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== 'Tab' || panel.current === null) return;
    const items = focusables(panel.current);
    const first = items[0];
    const last = items[items.length - 1];
    if (first === undefined || last === undefined) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
}
