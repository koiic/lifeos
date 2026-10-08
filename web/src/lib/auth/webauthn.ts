// Passkey ceremonies (AUTH-2, spec 12.3) through @simplewebauthn/browser. The server sends the
// WebAuthn options as JSON and verifies the JSON credential it gets back.
import {
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
  startAuthentication,
  startRegistration,
} from '@simplewebauthn/browser';

/** Options as the server returns them (the generated type is an open object). */
export type ServerOptions = Record<string, unknown>;
/** The credential's JSON form, as the server's `credential` fields take it. */
export type CredentialJSON = Record<string, unknown>;

/** She dismissed the prompt, or it timed out: not an error to report, a choice to offer again. */
export class PasskeyCancelled extends Error {
  constructor() {
    super('The passkey prompt was dismissed.');
    this.name = 'PasskeyCancelled';
  }
}

function cancellation(error: unknown): unknown {
  return error instanceof Error && error.name === 'NotAllowedError'
    ? new PasskeyCancelled()
    : error;
}

export async function createPasskey(options: ServerOptions): Promise<CredentialJSON> {
  try {
    return (await startRegistration({
      optionsJSON: options as unknown as PublicKeyCredentialCreationOptionsJSON,
    })) as unknown as CredentialJSON;
  } catch (error) {
    throw cancellation(error);
  }
}

export async function signWithPasskey(options: ServerOptions): Promise<CredentialJSON> {
  try {
    return (await startAuthentication({
      optionsJSON: options as unknown as PublicKeyCredentialRequestOptionsJSON,
    })) as unknown as CredentialJSON;
  } catch (error) {
    throw cancellation(error);
  }
}
