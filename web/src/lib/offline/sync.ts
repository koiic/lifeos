import { countOutbox, dequeue, getOutbox, markAttempt } from './outbox';
import type { FailedSyncItem, OutboxItem, SyncState } from './types';

export type SyncEvent =
  | { type: 'synced'; item: OutboxItem }
  | { type: 'rollback'; item: OutboxItem; status: number }
  | { type: 'unauthorized'; item: OutboxItem }
  | { type: 'error'; item: OutboxItem; error: unknown };

type SyncListener = (event: SyncEvent) => void;
type StateListener = (state: SyncState) => void;

let syncState: SyncState = {
  pendingCount: 0,
  isSyncing: false,
  isPaused: false,
  lastSyncedAt: null,
  lastError: null,
};

const failedItems: FailedSyncItem[] = [];
const eventListeners = new Set<SyncListener>();
const stateListeners = new Set<StateListener>();

export function getSyncState(): SyncState {
  return { ...syncState };
}

export function getFailedItems(): FailedSyncItem[] {
  return [...failedItems];
}

export function resetSyncState(): void {
  syncState = {
    pendingCount: 0,
    isSyncing: false,
    isPaused: false,
    lastSyncedAt: null,
    lastError: null,
  };
  failedItems.length = 0;
  notifyState();
}

export function unpauseSync(): void {
  syncState.isPaused = false;
  notifyState();
}

export function subscribeSync(listener: SyncListener): () => void {
  eventListeners.add(listener);
  return () => {
    eventListeners.delete(listener);
  };
}

export function subscribeSyncState(listener: StateListener): () => void {
  stateListeners.add(listener);
  listener(getSyncState());
  return () => {
    stateListeners.delete(listener);
  };
}

function notifyEvent(event: SyncEvent): void {
  for (const listener of eventListeners) {
    listener(event);
  }
}

function notifyState(): void {
  const current = getSyncState();
  for (const listener of stateListeners) {
    listener(current);
  }
}

export async function refreshPendingCount(): Promise<number> {
  const count = await countOutbox();
  syncState.pendingCount = count;
  notifyState();
  return count;
}

export async function flushOutbox(): Promise<void> {
  if (syncState.isSyncing || syncState.isPaused) {
    return;
  }

  syncState.isSyncing = true;
  syncState.lastError = null;
  notifyState();

  try {
    const items = await getOutbox();
    syncState.pendingCount = items.length;
    notifyState();

    for (const item of items) {
      if (syncState.isPaused) {
        break;
      }

      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          'X-LifeOS-Client': 'web',
          'Idempotency-Key': item.id,
        };

        const res = await fetch(item.path, {
          method: item.method,
          headers,
          ...(item.body !== undefined && item.body !== null
            ? { body: JSON.stringify(item.body) }
            : {}),
        });

        if (res.ok) {
          await dequeue(item.id);
          notifyEvent({ type: 'synced', item });
          syncState.lastSyncedAt = new Date().toISOString();
        } else if (res.status === 401) {
          syncState.isPaused = true;
          notifyEvent({ type: 'unauthorized', item });
          break;
        } else if (res.status === 409 || res.status === 422) {
          await dequeue(item.id);
          failedItems.push({
            item,
            status: res.status,
            message: `Request failed with status ${String(res.status)}`,
            failedAt: new Date().toISOString(),
          });
          notifyEvent({ type: 'rollback', item, status: res.status });
        } else {
          // 429, 5xx, or other server errors: keep and back off
          await markAttempt(item.id);
          syncState.lastError = `Server error ${String(res.status)}`;
          notifyEvent({
            type: 'error',
            item,
            error: new Error(`HTTP ${String(res.status)}`),
          });
          break; // preserve FIFO ordering
        }
      } catch (err) {
        // Network failure
        await markAttempt(item.id);
        syncState.lastError = err instanceof Error ? err.message : 'Network error';
        notifyEvent({ type: 'error', item, error: err });
        break; // preserve FIFO ordering
      }
    }
  } finally {
    syncState.isSyncing = false;
    syncState.pendingCount = await countOutbox();
    notifyState();
  }
}

// Auto-sync initialization (spec 11.5 rule 2)
let autoSyncInitialized = false;

export function initAutoSync(): () => void {
  if (autoSyncInitialized || typeof window === 'undefined') {
    return () => {};
  }
  autoSyncInitialized = true;

  const handleOnline = () => {
    void flushOutbox();
  };

  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      void flushOutbox();
    }
  };

  window.addEventListener('online', handleOnline);
  document.addEventListener('visibilitychange', handleVisibilityChange);
  const intervalId = setInterval(() => {
    void flushOutbox();
  }, 30_000);

  // Initial refresh of pending count and flush
  void refreshPendingCount().then(() => flushOutbox());

  return () => {
    window.removeEventListener('online', handleOnline);
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    clearInterval(intervalId);
    autoSyncInitialized = false;
  };
}
