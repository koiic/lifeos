import { type DBSchema, type IDBPDatabase, openDB } from 'idb';

import type { OutboxItem } from './types';

export interface LifeOSDB extends DBSchema {
  outbox: {
    key: string;
    value: OutboxItem;
    indexes: { by_created_at: string };
  };
  crypto_keys: {
    key: string;
    value: { name: string; key: CryptoKey };
  };
  query_cache: {
    key: string;
    value: { id: string; iv: string; ciphertext: string; updated_at: string };
  };
}

const DB_NAME = 'lifeos_offline';
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<LifeOSDB>> | null = null;

export function getDB(): Promise<IDBPDatabase<LifeOSDB>> {
  if (!dbPromise) {
    dbPromise = openDB<LifeOSDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('outbox')) {
          const outboxStore = db.createObjectStore('outbox', { keyPath: 'id' });
          outboxStore.createIndex('by_created_at', 'created_at');
        }
        if (!db.objectStoreNames.contains('crypto_keys')) {
          db.createObjectStore('crypto_keys', { keyPath: 'name' });
        }
        if (!db.objectStoreNames.contains('query_cache')) {
          db.createObjectStore('query_cache', { keyPath: 'id' });
        }
      },
    });
  }
  return dbPromise;
}

export async function closeDB(): Promise<void> {
  if (dbPromise) {
    const db = await dbPromise;
    db.close();
    dbPromise = null;
  }
}

export async function clearAllOfflineData(): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(['outbox', 'crypto_keys', 'query_cache'], 'readwrite');
  await Promise.all([
    tx.objectStore('outbox').clear(),
    tx.objectStore('crypto_keys').clear(),
    tx.objectStore('query_cache').clear(),
    tx.done,
  ]);
}
