import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearOutbox, countOutbox, dequeue, enqueue, getOutbox, markAttempt } from './outbox';

describe('[CHK-5] outbox', () => {
  beforeEach(async () => {
    await clearOutbox();
  });

  it('enqueues items with uuid, iso timestamp and attempts 0', async () => {
    const item = await enqueue({
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-10',
      body: { mood: 4 },
    });

    expect(item.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
    expect(item.attempts).toBe(0);
    expect(typeof item.created_at).toBe('string');
    expect(item.method).toBe('PUT');
    expect(item.path).toBe('/api/v1/daily-logs/2026-10-10');

    const count = await countOutbox();
    expect(count).toBe(1);
  });

  it('maintains strict FIFO ordering by created_at', async () => {
    await enqueue({
      id: 'first-id',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-08',
      body: { mood: 3 },
      created_at: '2026-10-08T10:00:00.000Z',
    });

    await enqueue({
      id: 'second-id',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-09',
      body: { mood: 4 },
      created_at: '2026-10-09T10:00:00.000Z',
    });

    await enqueue({
      id: 'third-id',
      method: 'PUT',
      path: '/api/v1/daily-logs/2026-10-10',
      body: { mood: 5 },
      created_at: '2026-10-10T10:00:00.000Z',
    });

    const items = await getOutbox();
    expect(items.map((i) => i.id)).toEqual(['first-id', 'second-id', 'third-id']);
  });

  it('increments attempts on markAttempt', async () => {
    const item = await enqueue({
      method: 'POST',
      path: '/api/v1/notes',
      body: { title: 'Test note' },
    });
    expect(item.attempts).toBe(0);

    await markAttempt(item.id);
    const [updated] = await getOutbox();
    expect(updated?.attempts).toBe(1);

    await markAttempt(item.id);
    const [updatedAgain] = await getOutbox();
    expect(updatedAgain?.attempts).toBe(2);
  });

  it('removes item on dequeue', async () => {
    const item1 = await enqueue({ method: 'PUT', path: '/api/v1/a', body: {} });
    const item2 = await enqueue({ method: 'PUT', path: '/api/v1/b', body: {} });

    expect(await countOutbox()).toBe(2);

    await dequeue(item1.id);
    const remaining = await getOutbox();
    expect(remaining).toHaveLength(1);
    expect(remaining[0]?.id).toBe(item2.id);
  });
});
