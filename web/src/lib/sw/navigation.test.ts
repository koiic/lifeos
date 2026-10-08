import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { NAVIGATION_TIMEOUT_MS, networkThenShell } from './navigation';

const page = new Response('from the network', { status: 200 });
const shell = new Response('the cached shell', { status: 200 });

function never(): Promise<Response> {
  return new Promise(() => undefined);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('navigations (spec 11.3: network first, 3 s timeout, then the cached shell)', () => {
  it('the timeout is 3 s', () => {
    expect(NAVIGATION_TIMEOUT_MS).toBe(3000);
  });

  it('a quick network answer is used', async () => {
    const result = networkThenShell(
      () => Promise.resolve(page),
      () => Promise.resolve(shell),
    );
    await expect(result).resolves.toBe(page);
  });

  it('a network error page is still the network answer (not replaced by the shell)', async () => {
    const notFound = new Response('gone', { status: 404 });
    const result = networkThenShell(
      () => Promise.resolve(notFound),
      () => Promise.resolve(shell),
    );
    await expect(result).resolves.toBe(notFound);
  });

  it('offline: the shell', async () => {
    const result = networkThenShell(
      () => Promise.reject(new TypeError('Failed to fetch')),
      () => Promise.resolve(shell),
    );
    await expect(result).resolves.toBe(shell);
  });

  it('slower than 3 s: the shell at 3 s, and the request is aborted', async () => {
    let signal: AbortSignal | undefined;
    const settled = vi.fn();
    const result = networkThenShell(
      (abort) => {
        signal = abort;
        return never();
      },
      () => Promise.resolve(shell),
    ).then((response) => {
      settled(response);
      return response;
    });
    await vi.advanceTimersByTimeAsync(2999);
    expect(settled).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await expect(result).resolves.toBe(shell);
    expect(signal?.aborted).toBe(true);
  });
});
