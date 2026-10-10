import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearOutbox, countOutbox, enqueue, getOutbox } from './outbox';
import { flushOutbox, getSyncState, resetSyncState, subscribeSync } from './sync';

describe('[CHK-5] sync engine', () => {
  beforeEach(async () => {
    await clearOutbox();
    resetSyncState();
    vi.restoreAllMocks();
  });

  it('flushes items in strict FIFO order sending Idempotency-Key header', async () => {
    const item1 = await enqueue({
      id: '00000000-0000-0000-0000-000000000001',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-09',
      body: { mood: 3 },
      created_at: '2026-10-09T08:00:00.000Z',
    });

    const item2 = await enqueue({
      id: '00000000-0000-0000-0000-000000000002',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-10',
      body: { mood: 4 },
      created_at: '2026-10-10T08:00:00.000Z',
    });

    const calls: { url: string; headers: HeadersInit; method: string }[] = [];
    const mockFetch = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      calls.push({
        url: String(url),
        headers: (init?.headers ?? {}) as HeadersInit,
        method: init?.method ?? 'GET',
      });
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    vi.stubGlobal('fetch', mockFetch);

    await flushOutbox();

    expect(calls).toHaveLength(2);
    expect(calls[0]?.url).toBe('/api/v1/daily-logs/2026-10-09');
    expect((calls[0]?.headers as Record<string, string>)['Idempotency-Key']).toBe(item1.id);
    expect((calls[0]?.headers as Record<string, string>)['X-LifeOS-Client']).toBe('web');

    expect(calls[1]?.url).toBe('/api/v1/daily-logs/2026-10-10');
    expect((calls[1]?.headers as Record<string, string>)['Idempotency-Key']).toBe(item2.id);

    expect(await countOutbox()).toBe(0);
    expect(getSyncState().pendingCount).toBe(0);
  });

  it('retains item and applies retry backoff on 5xx or network error', async () => {
    const item = await enqueue({
      id: '00000000-0000-0000-0000-000000000003',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-10',
      body: { mood: 4 },
    });

    const mockFetch = vi.fn().mockResolvedValue(new Response('Server error', { status: 500 }));
    vi.stubGlobal('fetch', mockFetch);

    await flushOutbox();

    // Item kept in outbox with incremented attempts
    const items = await getOutbox();
    expect(items).toHaveLength(1);
    expect(items[0]?.id).toBe(item.id);
    expect(items[0]?.attempts).toBe(1);

    const state = getSyncState();
    expect(state.pendingCount).toBe(1);
    expect(state.lastError).toBeDefined();
  });

  it('removes item and triggers rollback on 422 or 409 conflict', async () => {
    const item = await enqueue({
      id: '00000000-0000-0000-0000-000000000004',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-10',
      body: { mood: 4 },
    });

    const mockFetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Unprocessable' }), { status: 422 }),
      );
    vi.stubGlobal('fetch', mockFetch);

    const rollbackHandler = vi.fn();
    const unsubscribe = subscribeSync((event) => {
      if (event.type === 'rollback') {
        rollbackHandler(event.item);
      }
    });

    await flushOutbox();
    unsubscribe();

    // Removed from outbox on 422
    expect(await countOutbox()).toBe(0);
    expect(rollbackHandler).toHaveBeenCalledWith(expect.objectContaining({ id: item.id }));
  });

  it('pauses sync engine on 401 unauthenticated response', async () => {
    await enqueue({
      id: '00000000-0000-0000-0000-000000000005',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-10',
      body: { mood: 4 },
    });

    const mockFetch = vi.fn().mockResolvedValue(new Response('Unauthorized', { status: 401 }));
    vi.stubGlobal('fetch', mockFetch);

    await flushOutbox();

    // Outbox item kept, sync paused
    expect(await countOutbox()).toBe(1);
    expect(getSyncState().isPaused).toBe(true);

    // Subsequent flush does not call fetch while paused
    mockFetch.mockClear();
    await flushOutbox();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
