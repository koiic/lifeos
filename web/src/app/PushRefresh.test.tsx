import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { refreshSubscription } from '../lib/push/push';
import { PushRefresh } from './PushRefresh';

vi.mock('../lib/push/push', () => ({ refreshSubscription: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.mocked(refreshSubscription).mockReset();
});

describe('push subscription on every app start (spec 10.5)', () => {
  it('re-registers once when the signed-in app starts', () => {
    vi.mocked(refreshSubscription).mockResolvedValue(undefined);
    const { rerender } = render(<PushRefresh />);
    rerender(<PushRefresh />);
    expect(refreshSubscription).toHaveBeenCalledOnce();
  });

  it('a failure (offline, signed out) is quiet: the next start tries again', async () => {
    vi.mocked(refreshSubscription).mockRejectedValue(new TypeError('offline'));
    const { container } = render(<PushRefresh />);
    await vi.waitFor(() => expect(refreshSubscription).toHaveBeenCalledOnce());
    await new Promise((settle) => setTimeout(settle, 0)); // the rejection is handled by now
    expect(container.innerHTML).toBe('');
  });
});
