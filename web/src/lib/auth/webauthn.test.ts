import { startAuthentication, startRegistration } from '@simplewebauthn/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createPasskey, PasskeyCancelled, signWithPasskey } from './webauthn';

vi.mock('@simplewebauthn/browser', () => ({
  startRegistration: vi.fn(),
  startAuthentication: vi.fn(),
}));

afterEach(() => {
  vi.mocked(startRegistration).mockReset();
  vi.mocked(startAuthentication).mockReset();
});

const creation = { challenge: 'c', rp: { id: 'localhost', name: 'Life OS' } };

describe('[AUTH-2] passkey ceremonies', () => {
  it('creates a passkey from the server options and returns the credential JSON', async () => {
    vi.mocked(startRegistration).mockResolvedValue({ id: 'cred' } as never);
    await expect(createPasskey(creation)).resolves.toEqual({ id: 'cred' });
    expect(startRegistration).toHaveBeenCalledWith({ optionsJSON: creation });
  });

  it('signs with a passkey from the server options', async () => {
    vi.mocked(startAuthentication).mockResolvedValue({ id: 'assertion' } as never);
    await expect(signWithPasskey({ challenge: 'c' })).resolves.toEqual({ id: 'assertion' });
    expect(startAuthentication).toHaveBeenCalledWith({ optionsJSON: { challenge: 'c' } });
  });

  it('a dismissed or timed-out prompt is a cancellation, not a failure', async () => {
    const dismissed = Object.assign(new Error('dismissed'), { name: 'NotAllowedError' });
    vi.mocked(startAuthentication).mockRejectedValue(dismissed);
    await expect(signWithPasskey({ challenge: 'c' })).rejects.toBeInstanceOf(PasskeyCancelled);
  });

  it('other errors pass through', async () => {
    vi.mocked(startRegistration).mockRejectedValue(new Error('no authenticator'));
    await expect(createPasskey(creation)).rejects.toThrow('no authenticator');
  });
});
