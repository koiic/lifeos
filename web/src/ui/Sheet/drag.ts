/** Spec 5.5 drag handle (CR-024): pure rules for the swipe-down-to-close gesture. */

/** A drag shorter than this never closes, so a short sheet still needs a deliberate swipe. */
const MIN_CLOSE_DRAG_PX = 48;

/** How far the sheet follows the pointer: down only. */
export function dragOffset(startY: number, currentY: number): number {
  return Math.max(0, currentY - startY);
}

/** Close when dragged past a quarter of the sheet's height (and at least 48 px). */
export function shouldClose(offset: number, sheetHeight: number): boolean {
  return offset > Math.max(sheetHeight / 4, MIN_CLOSE_DRAG_PX);
}
