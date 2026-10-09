// Shared journey steps: a simulated passkey authenticator and registering from an invite.
import { type CDPSession, expect, type Page } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';

const reg = copy.auth.register;

export interface Authenticator {
  cdp: CDPSession;
  id: string;
}

/** A platform authenticator with user verification, like Face ID (AUTH-2: UV required). */
export async function addAuthenticator(page: Page, userVerified = true): Promise<Authenticator> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: userVerified,
      automaticPresenceSimulation: true,
    },
  });
  return { cdp, id: authenticatorId };
}

/** [ONB-1] J1 step 3: in a browser tab the install guide comes next; she carries on in the tab. */
export async function carryOnInBrowser(page: Page) {
  await expect(page.getByRole('heading', { name: copy.install.title })).toBeVisible();
  await page.getByRole('button', { name: copy.install.continue }).click();
  await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();
}

export async function registerWithPasskey(page: Page, token: string, email = 'zee@example.test') {
  await page.goto(`/register?token=${token}`);
  await page.getByLabel(reg.name).fill('Zee');
  await expect(page.getByLabel(reg.email)).toHaveValue(email);
  await page.getByRole('button', { name: reg.createPasskey }).click();
  const codes = page.getByRole('list', { name: copy.auth.codes.list });
  await expect(codes.getByRole('listitem')).toHaveCount(10);
  const recoveryCodes = await codes.getByRole('listitem').allTextContents();
  await page.getByRole('button', { name: copy.auth.codes.done }).click();
  await carryOnInBrowser(page);
  return recoveryCodes;
}
