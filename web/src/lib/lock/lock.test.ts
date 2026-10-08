import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_LOCK_TIMEOUT_S, isLockDue } from './rules';
import { HIDDEN_AT_KEY, LOCKED_KEY, useLockStore } from './store';
import { startLockWatch } from './watch';

describe('[AUTH-6] lock rules (spec 11.6)', () => {
  it('the default timeout is 5 minutes', () => {
    expect(DEFAULT_LOCK_TIMEOUT_S).toBe(300);
  });

  it('locks only after more than the timeout in the background', () => {
    expect(isLockDue(null, 1_000_000, 300)).toBe(false);
    expect(isLockDue(0, 300_000, 300)).toBe(false);
    expect(isLockDue(0, 300_001, 300)).toBe(true);
  });

  it('a clock that went backwards locks: how long she was away cannot be known', () => {
    expect(isLockDue(500_000, 100, 300)).toBe(true);
  });
});

/** document.visibilityState is read-only in jsdom: drive it for the watcher. */
function setVisibility(state: 'hidden' | 'visible') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('[AUTH-6] lock watch (spec 11.6)', () => {
  let now = 0;
  let stop: () => void = () => undefined;
  const clock = () => now;
  // The page's monotonic clock (performance.now): it never goes back.
  let mono = 0;
  const elapsed = () => mono;
  const advance = (ms: number) => {
    now += ms;
    mono += ms;
  };

  beforeEach(() => {
    now = 1_000_000;
    mono = 0;
    localStorage.clear();
    useLockStore.getState().reset();
    setVisibility('visible');
  });

  afterEach(() => {
    stop();
  });

  it('covers the app as soon as it is hidden, so the app switcher shows the lock state', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    expect(useLockStore.getState().covered).toBe(true);
    expect(localStorage.getItem(HIDDEN_AT_KEY)).toBe(String(now));
  });

  it('back within the timeout: uncovered and not locked', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    advance(299_000);
    setVisibility('visible');
    expect(useLockStore.getState()).toMatchObject({ locked: false, covered: false });
    expect(localStorage.getItem(HIDDEN_AT_KEY)).toBeNull();
  });

  it('back after more than the timeout: locked', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    advance(301_000);
    setVisibility('visible');
    expect(useLockStore.getState()).toMatchObject({ locked: true, covered: false });
  });

  it('a cold start after a long time in the background opens locked', () => {
    localStorage.setItem(HIDDEN_AT_KEY, String(now - 600_000));
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    expect(useLockStore.getState().locked).toBe(true);
  });

  it('a reload while locked stays locked, whatever the clock says (no unlock by clock change)', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    advance(400_000);
    setVisibility('visible');
    stop();
    useLockStore.setState({ locked: false, covered: false }); // a fresh page
    now -= 1_000_000; // the device clock set back
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    expect(useLockStore.getState().locked).toBe(true);
    useLockStore.getState().unlock();
    expect(localStorage.getItem(LOCKED_KEY)).toBeNull();
  });

  it('the phone slept: the page clock barely moved, the wall clock says 30 minutes — locks', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    mono += 2_000;
    now += 30 * 60_000;
    setVisibility('visible');
    expect(useLockStore.getState().locked).toBe(true);
  });

  it('setting the clock back while in the background does not avoid the lock', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    mono += 400_000;
    now -= 3_600_000;
    setVisibility('visible');
    expect(useLockStore.getState().locked).toBe(true);
  });

  it('a cold start with the clock set back opens locked (time away unknown)', () => {
    localStorage.setItem(HIDDEN_AT_KEY, String(now + 3_600_000));
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    expect(useLockStore.getState().locked).toBe(true);
  });

  it('a cold start soon after opens unlocked', () => {
    localStorage.setItem(HIDDEN_AT_KEY, String(now - 10_000));
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    expect(useLockStore.getState().locked).toBe(false);
  });

  it('unlocking clears the lock and the stored time', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    setVisibility('hidden');
    advance(400_000);
    setVisibility('visible');
    useLockStore.getState().unlock();
    expect(useLockStore.getState().locked).toBe(false);
    expect(localStorage.getItem(HIDDEN_AT_KEY)).toBeNull();
  });

  it('stopping removes the listener', () => {
    stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
    stop();
    setVisibility('hidden');
    expect(useLockStore.getState().covered).toBe(false);
  });

  it('works when storage is unavailable (private browsing)', () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };
    try {
      stop = startLockWatch({ now: clock, elapsed, timeoutS: 300 });
      setVisibility('hidden');
      advance(400_000);
      setVisibility('visible');
      expect(useLockStore.getState().locked).toBe(true);
    } finally {
      Storage.prototype.setItem = original;
    }
  });
});

describe('[AUTH-6] the lock is decided when the page loads, before anything renders', () => {
  afterEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  async function freshStore() {
    vi.resetModules();
    return (await import('./store')).useLockStore.getState();
  }

  it('a page that was locked opens locked', async () => {
    localStorage.setItem(LOCKED_KEY, '1');
    expect((await freshStore()).locked).toBe(true);
  });

  it('a page away for longer than the default timeout opens locked', async () => {
    localStorage.setItem(HIDDEN_AT_KEY, String(Date.now() - 301_000));
    expect((await freshStore()).locked).toBe(true);
  });

  it('a fresh page opens unlocked', async () => {
    expect((await freshStore()).locked).toBe(false);
  });
});
