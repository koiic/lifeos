import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearCryptoKey, decrypt, encrypt, getOrGenerateKey } from './crypto';

describe('[CHK-5] offline crypto', () => {
  beforeEach(async () => {
    await clearCryptoKey();
  });

  it('generates a non-extractable AES-GCM 256 key', async () => {
    const key = await getOrGenerateKey();
    expect(key.algorithm.name).toBe('AES-GCM');
    expect(key.extractable).toBe(false);
    expect(key.usages).toContain('encrypt');
    expect(key.usages).toContain('decrypt');

    // Reusing returns the same persisted key
    const sameKey = await getOrGenerateKey();
    expect(sameKey).toBe(key);
  });

  it('encrypts and decrypts payload roundtrip', async () => {
    const payload = JSON.stringify({
      user: 'Zee',
      dailyLogs: [{ date: '2026-10-10', mood: 4 }],
    });

    const encrypted = await encrypt(payload);
    expect(encrypted.ciphertext).toBeDefined();
    expect(encrypted.iv).toBeDefined();
    expect(encrypted.ciphertext).not.toContain('Zee');

    const decrypted = await decrypt(encrypted);
    expect(decrypted).toBe(payload);
    expect(JSON.parse(decrypted)).toEqual({
      user: 'Zee',
      dailyLogs: [{ date: '2026-10-10', mood: 4 }],
    });
  });

  it('fails decryption on tampered ciphertext', async () => {
    const encrypted = await encrypt('secret health note');
    // Tamper with base64 ciphertext
    const tampered = {
      ...encrypted,
      ciphertext: encrypted.ciphertext.slice(0, -4) + 'AAAA',
    };

    await expect(decrypt(tampered)).rejects.toThrow();
  });
});
