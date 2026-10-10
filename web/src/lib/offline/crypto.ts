import { getDB } from './db';

const KEY_NAME = 'query_cache_key';

let cachedKey: CryptoKey | null = null;

function bufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    const byte = bytes[i];
    if (byte !== undefined) {
      binary += String.fromCharCode(byte);
    }
  }
  return btoa(binary);
}

function base64ToBuffer(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export async function getOrGenerateKey(): Promise<CryptoKey> {
  if (cachedKey) {
    return cachedKey;
  }

  const db = await getDB();
  const existing = await db.get('crypto_keys', KEY_NAME);
  if (existing) {
    cachedKey = existing.key;
    return cachedKey;
  }

  // Generate non-extractable AES-GCM 256-bit key (spec 11.4)
  const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, [
    'encrypt',
    'decrypt',
  ]);

  await db.put('crypto_keys', { name: KEY_NAME, key });
  cachedKey = key;
  return key;
}

export async function clearCryptoKey(): Promise<void> {
  cachedKey = null;
  const db = await getDB();
  await db.delete('crypto_keys', KEY_NAME);
}

export interface EncryptedPayload {
  iv: string;
  ciphertext: string;
}

export async function encrypt(plaintext: string): Promise<EncryptedPayload> {
  const key = await getOrGenerateKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoder = new TextEncoder();
  const encoded = encoder.encode(plaintext);

  const encryptedBuffer = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoded);

  return {
    iv: bufferToBase64(iv),
    ciphertext: bufferToBase64(encryptedBuffer),
  };
}

export async function decrypt(payload: EncryptedPayload): Promise<string> {
  const key = await getOrGenerateKey();
  const iv = base64ToBuffer(payload.iv);
  const ciphertext = base64ToBuffer(payload.ciphertext);

  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as BufferSource },
    key,
    ciphertext as BufferSource,
  );

  const decoder = new TextDecoder();
  return decoder.decode(decryptedBuffer);
}
