import { create } from 'zustand';

import { DEFAULT_LOCK_TIMEOUT_S, isLockDue } from './rules';

/** Where the time the app went into the background is kept, so a cold start can lock too. */
export const HIDDEN_AT_KEY = 'lifeos.hiddenAt';
/** Set while locked: a reload or cold start stays locked until she unlocks, whatever the clock. */
export const LOCKED_KEY = 'lifeos.locked';

export interface LockState {
  /** The lock screen is up: nothing of her data is rendered until she unlocks (11.6). */
  locked: boolean;
  /** The app is in the background: covered so the app switcher snapshot shows no content. */
  covered: boolean;
  lock: () => void;
  unlock: () => void;
  setCovered: (covered: boolean) => void;
  /** Sign-out: no lock, no cover, nothing stored. */
  reset: () => void;
}

// Storage can be blocked (private browsing): the in-memory state still works for this page.
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // blocked: nothing to do
  }
}

export function readHiddenAt(): number | null {
  const value = read(HIDDEN_AT_KEY);
  return value === null ? null : Number(value);
}

export function writeHiddenAt(value: number | null): void {
  write(HIDDEN_AT_KEY, value === null ? null : String(value));
}

export function wasLocked(): boolean {
  return read(LOCKED_KEY) !== null;
}

/**
 * Decided when the page loads, before anything renders (11.6: "the overlay is rendered before any
 * data"): a page that was locked, or away longer than the timeout, opens locked.
 */
function lockedAtLoad(): boolean {
  return wasLocked() || isLockDue(readHiddenAt(), Date.now(), DEFAULT_LOCK_TIMEOUT_S);
}

export const useLockStore = create<LockState>()((set) => ({
  locked: lockedAtLoad(),
  covered: false,
  lock: () => {
    write(LOCKED_KEY, '1');
    set({ locked: true });
  },
  unlock: () => {
    write(LOCKED_KEY, null);
    writeHiddenAt(null);
    set({ locked: false });
  },
  setCovered: (covered) => set({ covered }),
  reset: () => {
    write(LOCKED_KEY, null);
    writeHiddenAt(null);
    set({ locked: false, covered: false });
  },
}));
