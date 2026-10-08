import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../copy/en-GB';
import { REASON } from '../lib/auth/session';
import { signWithPasskey } from '../lib/auth/webauthn';
import { HIDDEN_AT_KEY, LOCKED_KEY, useLockStore } from '../lib/lock/store';
import { fakeApi, problem, type Route } from '../lib/testing/fakeApi';
import { renderRoute } from '../lib/testing/renderRoute';
import { AppLock } from './AppLock';

vi.mock('../lib/auth/webauthn', async (original) => ({
  ...(await original<typeof import('../lib/auth/webauthn')>()),
  signWithPasskey: vi.fn(),
}));

const t = copy.lock;
const PASSKEYS = 'GET /api/v1/auth/passkeys';
const UNLOCK_PIN = 'POST /api/v1/auth/app-lock/unlock';
const REAUTH_OPTIONS = 'POST /api/v1/auth/reauth/options';
const REAUTH_VERIFY = 'POST /api/v1/auth/reauth/verify';
const ONE_PASSKEY = { body: { items: [{ id: 'p1' }], next_cursor: null } };

function setup(routes: Record<string, Route> = {}) {
  return fakeApi({ [PASSKEYS]: ONE_PASSKEY, ...routes });
}

function open() {
  return renderRoute(
    <AppLock>
      <p>her data</p>
    </AppLock>,
    { path: '/today', url: '/today' },
  );
}

function enterPin(pin: string) {
  fireEvent.change(screen.getByLabelText(t.pin), { target: { value: pin } });
  fireEvent.click(screen.getByRole('button', { name: t.unlock }));
}

beforeEach(() => {
  localStorage.clear();
  useLockStore.setState({ locked: true, covered: false });
  vi.mocked(signWithPasskey).mockResolvedValue({ id: 'assertion' } as never);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(signWithPasskey).mockReset();
  useLockStore.setState({ locked: false, covered: false });
});

describe('[AUTH-6] app lock (spec 11.6)', () => {
  it('while locked, the lock screen shows and none of her data is rendered', () => {
    setup();
    open();
    expect(screen.getByRole('dialog', { name: t.title })).toBeDefined();
    expect(screen.queryByText('her data')).toBeNull();
  });

  it('unlocks with a passkey (user verification, purpose unlock)', async () => {
    const api = setup({ [REAUTH_OPTIONS]: { body: { challenge: 'u' } }, [REAUTH_VERIFY]: {} });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.passkey }));
    expect(await screen.findByText('her data')).toBeDefined();
    expect(api.bodies(REAUTH_OPTIONS)).toEqual([{ purpose: 'unlock' }]);
    expect(signWithPasskey).toHaveBeenCalledWith({ challenge: 'u' });
    expect(api.bodies(REAUTH_VERIFY)).toEqual([{ credential: { id: 'assertion' } }]);
    expect(useLockStore.getState().locked).toBe(false);
  });

  it('unlocks with her 6-digit PIN', async () => {
    const api = setup({ [UNLOCK_PIN]: {} });
    open();
    enterPin('123456');
    expect(await screen.findByText('her data')).toBeDefined();
    expect(api.bodies(UNLOCK_PIN)).toEqual([{ pin: '123456' }]);
  });

  it('a wrong PIN says so and stays locked', async () => {
    setup({ [UNLOCK_PIN]: problem(401, REASON.wrongPin) });
    open();
    enterPin('000000');
    expect(await screen.findByText(t.wrongPin)).toBeDefined();
    expect(screen.queryByText('her data')).toBeNull();
  });

  it('after five wrong PINs the session has ended: full sign-in', async () => {
    setup({ [UNLOCK_PIN]: problem(401, REASON.pinLockedOut) });
    open();
    enterPin('000000');
    expect((await screen.findByTestId('arrived')).textContent).toBe('/signin');
  });

  it('without a PIN set, says to use the passkey', async () => {
    setup({ [UNLOCK_PIN]: problem(409, REASON.noPin) });
    open();
    enterPin('123456');
    expect(await screen.findByText(t.noPin)).toBeDefined();
  });

  it('a password account without passkeys gets no passkey button', async () => {
    setup({ [PASSKEYS]: { body: { items: [], next_cursor: null } } });
    open();
    expect(screen.getByLabelText(t.pin)).toBeDefined();
    // Once the (empty) list has loaded, the passkey button goes away.
    await waitFor(() => expect(screen.queryByRole('button', { name: t.passkey })).toBeNull());
  });

  it('signing out from the lock screen goes to sign-in', async () => {
    const api = setup({ 'POST /api/v1/auth/signout': {} });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.signOut }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/signin');
    expect(api.count('POST /api/v1/auth/signout')).toBe(1);
  });

  it('in the background the app is covered but kept, ready for a quick return', () => {
    setup();
    useLockStore.setState({ locked: false, covered: true });
    open();
    expect(screen.getByRole('dialog', { name: t.title })).toBeDefined();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    const data = screen.getByText('her data');
    expect(data.closest('[inert]')).not.toBeNull();
  });

  it('starts watching the background time when shown', () => {
    setup();
    useLockStore.setState({ locked: false, covered: false });
    open();
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(localStorage.getItem(HIDDEN_AT_KEY)).not.toBeNull();
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });

  it('offline: says it is the connection, not her PIN', async () => {
    setup();
    open();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    enterPin('123456');
    expect(await screen.findByText(copy.common.networkError)).toBeDefined();
  });

  it('the fifth wrong PIN also forgets her cached data and the lock (spec 11.4)', async () => {
    setup({ [UNLOCK_PIN]: problem(401, REASON.pinLockedOut), 'POST /api/v1/auth/signout': {} });
    const { queryClient } = open();
    queryClient.setQueryData(['today', '2026-10-08'], { secret: 'cached' });
    enterPin('000000');
    await screen.findByTestId('arrived');
    expect(queryClient.getQueryData(['today', '2026-10-08'])).toBeUndefined();
    expect(localStorage.getItem(LOCKED_KEY)).toBeNull();
  });

  it('while her passkeys are unknown (list failed), the passkey button is still offered', async () => {
    setup({ [PASSKEYS]: problem(503, 'down') });
    open();
    expect(await screen.findByRole('button', { name: t.passkey })).toBeDefined();
  });
});
