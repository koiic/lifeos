import { getDB } from './db';
import type { OutboxEnqueueInput, OutboxItem } from './types';

export async function enqueue(input: OutboxEnqueueInput): Promise<OutboxItem> {
  const db = await getDB();
  const item: OutboxItem = {
    id: input.id ?? crypto.randomUUID(),
    method: input.method,
    path: input.path,
    body: input.body,
    created_at: input.created_at ?? new Date().toISOString(),
    attempts: 0,
  };
  await db.put('outbox', item);
  return item;
}

export async function getOutbox(): Promise<OutboxItem[]> {
  const db = await getDB();
  return db.getAllFromIndex('outbox', 'by_created_at');
}

export async function countOutbox(): Promise<number> {
  const db = await getDB();
  return db.count('outbox');
}

export async function dequeue(id: string): Promise<void> {
  const db = await getDB();
  await db.delete('outbox', id);
}

export async function markAttempt(id: string): Promise<void> {
  const db = await getDB();
  const item = await db.get('outbox', id);
  if (item) {
    item.attempts += 1;
    await db.put('outbox', item);
  }
}

export async function clearOutbox(): Promise<void> {
  const db = await getDB();
  await db.clear('outbox');
}
