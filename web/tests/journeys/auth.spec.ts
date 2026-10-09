import { createHmac } from 'node:crypto';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import {
  addAuthenticator,
  type Authenticator,
  carryOnInBrowser,
  registerWithPasskey,
} from './session';
import { createInvite, expireRecentAuth } from './stack';

/**
 * T12 done-when (Chromium with a virtual WebAuthn authenticator, spec 15.1): register, sign out,
 * sign in, lock after the timeout, unlock, revoke a session — plus the password + authenticator
 * fallback and recovery-code sign-in. Runs against the real local stack (tests/journeys/stack.ts).
 */

const reg = copy.auth.register;
const signIn = copy.auth.signIn;
const sec = copy.settings.security;
const lock = copy.lock;

/** The same synced passkey on a second device (iCloud Keychain / Google Password Manager). */
async function copyPasskeys(from: Authenticator, to: Authenticator) {
  const { credentials } = await from.cdp.send('WebAuthn.getCredentials', {
    authenticatorId: from.id,
  });
  for (const credential of credentials) {
    await to.cdp.send('WebAuthn.addCredential', { authenticatorId: to.id, credential });
  }
}

/** Leave the app in the background for `seconds` (spec 11.6), on Playwright's clock. */
async function background(page: Page, seconds: number) {
  await setVisibility(page, 'hidden');
  await page.clock.fastForward(seconds * 1000);
  await setVisibility(page, 'visible');
}

async function setVisibility(page: Page, state: 'hidden' | 'visible') {
  await page.evaluate((value) => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
    document.dispatchEvent(new Event('visibilitychange'));
  }, state);
}

/** A new phone: the old authenticator (and its passkeys) gone, a fresh one in its place. */
async function newPhone(page: Page, old: Authenticator): Promise<Authenticator> {
  await old.cdp.send('WebAuthn.removeVirtualAuthenticator', { authenticatorId: old.id });
  return addAuthenticator(page);
}

async function signOutFromSettings(page: Page) {
  await page.goto('/settings/security');
  await page.getByRole('button', { name: sec.signOut }).click();
  await expect(page.getByRole('heading', { name: signIn.title })).toBeVisible();
}

async function signInWithRecoveryCode(page: Page, email: string, code: string) {
  await page.getByRole('button', { name: signIn.useRecoveryCode }).click();
  await page.getByLabel(signIn.email).fill(email);
  await page.getByLabel(signIn.recoveryCode).fill(code);
  await page.getByRole('button', { name: signIn.recoverySubmit }).click();
}

/** RFC 6238 (SHA-1, 6 digits, 30 s): what her authenticator app shows. */
function totp(secret: string, at: number): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const char of secret.replace(/=+$/, '')) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, '0');
  }
  const key = Buffer.from(bits.match(/.{8}/g)?.map((byte) => parseInt(byte, 2)) ?? []);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const mac = createHmac('sha1', key).update(counter).digest();
  const offset = (mac[mac.length - 1] ?? 0) & 0xf;
  const code = (mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return String(code).padStart(6, '0');
}

/**
 * The next code the server accepts after one used at `usedAt`: any code up to one step after a
 * used one counts as used (spec 12.3: no reuse within the window), so wait — as she would — for
 * the next 30 s step, then use the code one step ahead (within ±1).
 */
async function freshCode(page: Page, secret: string, usedAt: number): Promise<string> {
  const nextStepStart = (Math.floor(usedAt / 30_000) + 1) * 30_000;
  const wait = nextStepStart - Date.now() + 500;
  if (wait > 0) await page.waitForTimeout(wait);
  return totp(secret, Date.now() + 30_000);
}

test.describe('auth journeys (J1, J11)', () => {
  // Each journey is its own phone on its own network (addresses reserved for testing; the local API honours
  // CF-Connecting-IP, CR-015), so the failures one journey makes on purpose do not count towards
  // another's AUTH-7 lockout (5 failed sign-ins per 15 minutes per IP) when they run in parallel.
  test.beforeEach(async ({ context }, testInfo) => {
    // One address per test line in 198.18.0.0/15 (reserved for testing): unique in this file.
    const line = testInfo.line;
    await context.setExtraHTTPHeaders({
      'CF-Connecting-IP': `198.18.${String(Math.floor(line / 256))}.${String(line % 256)}`,
    });
  });

  test('[AUTH-1] an invite link that is not valid shows why', async ({ page }) => {
    await page.goto('/register?token=not-a-real-invite');
    await expect(page.getByText(reg.invalidTitle)).toBeVisible();
    await expect(page.getByLabel(reg.name)).toHaveCount(0);
  });

  test('[AUTH-1] [AUTH-2] [AUTH-4] [AUTH-5] [AUTH-6] register, sign out, sign in, lock, unlock, revoke', async ({
    page,
    browser,
  }) => {
    await page.clock.install();
    const phone = await addAuthenticator(page);

    // [AUTH-1] [AUTH-2] [AUTH-4] Register from the invite with a passkey; codes shown once.
    const token = createInvite('zee@example.test');
    const oldCodes = await registerWithPasskey(page, token);

    // [AUTH-5] The session cookie: HttpOnly, Secure, SameSite=Lax.
    const cookie = (await page.context().cookies()).find((c) => c.name === 'lo_session');
    expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Lax' });

    // [AUTH-1] The invite was single-use: opening it again is refused.
    await page.goto(`/register?token=${token}`);
    await expect(page.getByText(reg.invalidTitle)).toBeVisible();

    // [AUTH-6] Set her app-lock PIN.
    await page.goto('/settings/security');
    const pinSection = page.getByRole('region', { name: sec.pin.title });
    await pinSection.getByLabel(sec.pin.new).fill('246810');
    await pinSection.getByLabel(sec.pin.repeat).fill('246810');
    await pinSection.getByRole('button', { name: sec.pin.save }).click();
    await expect(pinSection.getByText(sec.pin.saved)).toBeVisible();
    // Registering just now counts as recent authentication (CR-017): nothing was asked.
    await expect(page.getByRole('dialog', { name: copy.auth.confirm.title })).toHaveCount(0);

    // [AUTH-5] Sign out, then sign in with the passkey (no email needed).
    await page.getByRole('button', { name: sec.signOut }).click();
    await expect(page.getByRole('heading', { name: signIn.title })).toBeVisible();
    await page.goto('/today');
    await expect(page).toHaveURL(/\/signin\?next=%2Ftoday$/);
    await page.getByRole('button', { name: signIn.passkey }).click();
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();

    // [AUTH-6] Within 5 minutes in the background: no lock.
    await background(page, 4 * 60);
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();

    // [AUTH-6] More than 5 minutes: the lock screen, and nothing of the app behind it.
    await background(page, 5 * 60 + 1);
    const lockScreen = page.getByRole('dialog', { name: lock.title });
    await expect(lockScreen).toBeVisible();
    await expect(page.getByRole('heading', { name: copy.today.title })).toHaveCount(0);

    // Unlock with the passkey (user verification).
    await lockScreen.getByRole('button', { name: lock.passkey }).click();
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();

    // Lock again; a cold start keeps it locked; unlock with the PIN (a wrong one first).
    await background(page, 6 * 60);
    await expect(lockScreen).toBeVisible();
    await page.reload();
    await expect(lockScreen).toBeVisible();
    await lockScreen.getByLabel(lock.pin).fill('000000');
    await lockScreen.getByRole('button', { name: lock.unlock, exact: true }).click();
    await expect(lockScreen.getByText(lock.wrongPin)).toBeVisible();
    await lockScreen.getByLabel(lock.pin).fill('246810');
    await lockScreen.getByRole('button', { name: lock.unlock, exact: true }).click();
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();

    // [AUTH-4] Later (recent authentication over, CR-017): new recovery codes ask "Confirm it's
    // you" first, answered with her passkey; then an old, unused code no longer works.
    expireRecentAuth('zee@example.test');
    await page.goto('/settings/security');
    await page
      .getByRole('region', { name: sec.codes.title })
      .getByRole('button', { name: sec.codes.regenerate })
      .click();
    const confirm = page.getByRole('dialog', { name: copy.auth.confirm.title });
    await expect(confirm).toBeVisible();
    await confirm.getByRole('button', { name: copy.auth.confirm.passkey }).click();
    await expect(
      page.getByRole('list', { name: copy.auth.codes.list }).getByRole('listitem'),
    ).toHaveCount(10);
    await page.getByRole('button', { name: copy.auth.codes.done }).click();

    // [AUTH-5] A second device with the same synced passkey; she revokes it from the phone.
    // (Run after the steps that use the phone's passkey: the two simulated authenticators'
    // signature counters drift apart once the copy is used, and the server rightly refuses a
    // counter that goes back (12.3); real synced passkeys report 0.)
    const laptop: BrowserContext = await browser.newContext({
      extraHTTPHeaders: { 'CF-Connecting-IP': '198.51.100.7' }, // the laptop's own network
    });
    const laptopPage = await laptop.newPage();
    await copyPasskeys(phone, await addAuthenticator(laptopPage));
    await laptopPage.goto('/signin');
    await laptopPage.getByRole('button', { name: signIn.passkey }).click();
    await expect(laptopPage.getByRole('heading', { name: copy.today.title })).toBeVisible();

    await page.goto('/settings/security');
    const sessions = page.getByRole('region', { name: sec.sessions.title });
    await expect(sessions.getByRole('listitem')).toHaveCount(2);
    // The laptop's device label comes from its user agent; it is the one that is not this device.
    await sessions
      .getByRole('listitem')
      .filter({ hasNotText: sec.sessions.thisDevice })
      .getByRole('button')
      .click();
    await expect(sessions.getByRole('listitem')).toHaveCount(1);

    await laptopPage.reload();
    await expect(laptopPage.getByRole('heading', { name: signIn.title })).toBeVisible();
    await laptop.close();

    // [AUTH-4] An old code she never used stopped working when she got new ones.
    await signOutFromSettings(page);
    await signInWithRecoveryCode(page, 'zee@example.test', oldCodes[1] ?? '');
    await expect(page.getByText(signIn.failed)).toBeVisible();
  });

  test('[AUTH-2] a passkey without user verification is not accepted', async ({ page }) => {
    await addAuthenticator(page, false);
    await page.goto(`/register?token=${createInvite('zee.nouv@example.test')}`);
    await page.getByLabel(reg.name).fill('Zee');
    await page.getByRole('button', { name: reg.createPasskey }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('list', { name: copy.auth.codes.list })).toHaveCount(0);
  });

  test('[AUTH-3] [AUTH-4] password and authenticator app, then a recovery code', async ({
    page,
  }) => {
    test.setTimeout(90_000); // waits up to 30 s for a fresh authenticator code
    let phone = await addAuthenticator(page);
    const email = 'zee.password@example.test';
    const password = 'a long enough passphrase';

    // [AUTH-3] Fallback registration: password, authenticator app, a confirmed code.
    await page.goto(`/register?token=${createInvite(email)}`);
    await page.getByLabel(reg.name).fill('Zee');
    await page.getByRole('button', { name: reg.usePassword }).click();
    await page.getByLabel(reg.password).fill(password);
    await page.getByRole('button', { name: reg.continue }).click();
    const link = page.getByRole('link', { name: reg.openAuthenticator });
    const uri = new URL((await link.getAttribute('href')) ?? '');
    const secret = uri.searchParams.get('secret') ?? '';
    const usedAt = Date.now();
    await page.getByLabel(reg.code).fill(totp(secret, usedAt));
    await page.getByRole('button', { name: reg.confirm }).click();

    // [AUTH-4] Ten codes, shown once.
    const codes = page.getByRole('list', { name: copy.auth.codes.list });
    await expect(codes.getByRole('listitem')).toHaveCount(10);
    const [firstCode, secondCode] = await codes.getByRole('listitem').allTextContents();
    await page.getByRole('button', { name: copy.auth.codes.done }).click();
    await carryOnInBrowser(page);

    // [AUTH-3] Sign out; sign in with password and the next code (a code is used once).
    await page.goto('/settings/security');
    await page.getByRole('button', { name: sec.signOut }).click();
    await page.getByRole('button', { name: signIn.usePassword }).click();
    await page.getByLabel(signIn.email).fill(email);
    await page.getByLabel(signIn.password).fill(password);
    await page.getByLabel(signIn.code).fill(await freshCode(page, secret, usedAt));
    await page.getByRole('button', { name: signIn.submit }).click();
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();

    // Settings: she adds a passkey to her password account (just signed in: no extra check).
    await page.goto('/settings/security');
    const passkeys = page.getByRole('region', { name: sec.passkeys.title });
    await passkeys.getByRole('button', { name: sec.passkeys.add }).click();
    await expect(passkeys.getByText(sec.passkeys.addedDone)).toBeVisible();
    await expect(passkeys.getByRole('listitem')).toHaveCount(1);

    // [AUTH-4] A new phone: a recovery code signs her in once she makes a new passkey (J11).
    await signOutFromSettings(page);
    phone = await newPhone(page, phone);
    await signInWithRecoveryCode(page, email, firstCode ?? '');
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();

    // [AUTH-4] The same code does not work twice; another one does.
    await signOutFromSettings(page);
    await signInWithRecoveryCode(page, email, firstCode ?? '');
    await expect(page.getByText(signIn.failed)).toBeVisible();
    await page.getByLabel(signIn.recoveryCode).fill(secondCode ?? '');
    await newPhone(page, phone);
    await page.getByRole('button', { name: signIn.recoverySubmit }).click();
    await expect(page.getByRole('heading', { name: copy.today.title })).toBeVisible();
  });
});
