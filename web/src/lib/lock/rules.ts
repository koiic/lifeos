/** Spec 11.6: the app locks after more than `app_lock_timeout_s` in the background. */

/** The spec default; the per-user setting arrives with `GET /me` (T09). */
export const DEFAULT_LOCK_TIMEOUT_S = 300;

/**
 * True when the app was hidden at `hiddenAt` (ms) and more than `timeoutS` has passed. A clock
 * that is now earlier than `hiddenAt` was set back: how long she was away is unknown, so lock.
 */
export function isLockDue(hiddenAt: number | null, now: number, timeoutS: number): boolean {
  if (hiddenAt === null) return false;
  return now < hiddenAt || now - hiddenAt > timeoutS * 1000;
}
