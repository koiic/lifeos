import { isLockDue } from './rules';
import { readHiddenAt, useLockStore, wasLocked, writeHiddenAt } from './store';

export interface LockWatchOptions {
  /** Wall-clock time in ms (stored, for a cold start). Injected in tests. */
  now?: () => number;
  /** The page's monotonic clock in ms (time in the background on this page). Injected in tests. */
  elapsed?: () => number;
  timeoutS: number;
}

/**
 * Spec 11.6: on `visibilitychange` to hidden, store the time and cover the app; on visible, lock
 * if more than the timeout passed by either the monotonic or the wall clock (so neither sleep
 * nor a changed device clock avoids it), else uncover. The stored wall-clock time covers a cold
 * start, and a page that was locked stays locked after a reload.
 * Returns a function that stops watching.
 */
export function startLockWatch({
  now = Date.now,
  elapsed = () => performance.now(),
  timeoutS,
}: LockWatchOptions): () => void {
  if (wasLocked() || isLockDue(readHiddenAt(), now(), timeoutS)) useLockStore.getState().lock();
  else if (document.visibilityState === 'visible') writeHiddenAt(null);

  // Both clocks: the monotonic one cannot be set back, but it can stop while the phone sleeps;
  // the wall clock keeps going while asleep. Either one past the timeout locks.
  let hiddenSince: number | null = null;
  let hiddenAt: number | null = null;

  const onChange = () => {
    if (document.visibilityState === 'hidden') {
      hiddenSince = elapsed();
      hiddenAt = now();
      writeHiddenAt(hiddenAt);
      useLockStore.getState().setCovered(true);
      return;
    }
    const due = isLockDue(hiddenSince, elapsed(), timeoutS) || isLockDue(hiddenAt, now(), timeoutS);
    if (due) {
      useLockStore.getState().lock();
    } else if (!useLockStore.getState().locked) {
      writeHiddenAt(null);
    }
    hiddenSince = null;
    hiddenAt = null;
    useLockStore.getState().setCovered(false);
  };

  document.addEventListener('visibilitychange', onChange);
  return () => document.removeEventListener('visibilitychange', onChange);
}
