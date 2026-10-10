export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface OutboxItem {
  id: string;
  method: HttpMethod;
  path: string;
  body: unknown;
  created_at: string;
  attempts: number;
}

export type OutboxEnqueueInput = Omit<OutboxItem, 'id' | 'created_at' | 'attempts'> & {
  id?: string;
  created_at?: string;
};

export interface SyncState {
  pendingCount: number;
  isSyncing: boolean;
  isPaused: boolean;
  lastSyncedAt: string | null;
  lastError: string | null;
}

export interface FailedSyncItem {
  item: OutboxItem;
  status: number;
  message: string;
  failedAt: string;
}
