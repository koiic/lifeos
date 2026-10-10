import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { REASON } from '../../lib/auth/session';
import { createPasskey, signWithPasskey } from '../../lib/auth/webauthn';
import { type FakeApi, fakeApi, problem, type Route } from '../../lib/testing/fakeApi';
import { meBody } from '../../lib/testing/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { SecurityScreen } from './SecurityScreen';

vi.mock('../../lib/auth/webauthn', async (original) => ({
  ...(await original<typeof import('../../lib/auth/webauthn')>()),
  createPasskey: vi.fn(),
  signWithPasskey: vi.fn(),
}));

const ME = 'GET /api/v1/me';
const t = copy.settings.security;
const SESSIONS = 'GET /api/v1/auth/sessions';
const PASSKEYS = 'GET /api/v1/auth/passkeys';
const ADD_OPTIONS = 'POST /api/v1/auth/passkeys/options';
const ADD_VERIFY = 'POST /api/v1/auth/passkeys/verify';
const REAUTH_OPTIONS = 'POST /api/v1/auth/reauth/options';
const REAUTH_VERIFY = 'POST /api/v1/auth/reauth/verify';
const APP_LOCK = 'PUT /api/v1/auth/app-lock';
const CODES_ROUTE = 'POST /api/v1/auth/recovery-codes';
const SIGN_OUT = 'POST /api/v1/auth/signout';
const CODES = Array.from({ length: 10 }, (_, i) => `abcd-efgh-${String(i)}`);

const PHONE = {
  id: 's-phone',
  device_label: 'iPhone · Safari',
  created_at: '2026-10-01T09:00:00Z',
  last_seen_at: '2026-10-08T08:00:00Z',
  current: true,
};
const LAPTOP = {
  id: 's-laptop',
  device_label: 'Mac · Chrome',
  created_at: '2026-09-20T09:00:00Z',
  last_seen_at: '2026-10-02T19:30:00Z',
  current: false,
};
const PASSKEY = {
  id: 'p-1',
  nickname: 'iCloud Keychain',
  created_at: '2026-10-01T09:00:00Z',
  last_used_at: null,
  backed_up: true,
};

function setup(extra: Record<string, Route> = {}): FakeApi {
  return fakeApi({
    [ME]: { body: meBody() },
    [SESSIONS]: { body: { items: [PHONE, LAPTOP], next_cursor: null } },
    [PASSKEYS]: { body: { items: [PASSKEY], next_cursor: null } },
    ...extra,
  });
}

function open() {
  return renderRoute(<SecurityScreen />, { path: '/settings/security', url: '/settings/security' });
}

function section(name: string) {
  return within(screen.getByRole('region', { name }));
}

beforeEach(() => {
  vi.mocked(createPasskey).mockResolvedValue({ id: 'new-credential' } as never);
  vi.mocked(signWithPasskey).mockResolvedValue({ id: 'assertion' } as never);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(createPasskey).mockReset();
  vi.mocked(signWithPasskey).mockReset();
});

describe('[AUTH-5] sessions: list and revoke in Settings', () => {
  it('lists her sessions, marking this device', async () => {
    setup();
    const { container } = open();
    const sessions = section(t.sessions.title);
    expect(await sessions.findByText('iPhone · Safari')).toBeDefined();
    expect(sessions.getByText('Mac · Chrome')).toBeDefined();
    expect(sessions.getByText(t.sessions.thisDevice)).toBeDefined();
    await expectNoAxeViolations(container);
  });

  it('revokes another session and refreshes the list', async () => {
    const api = setup({
      [SESSIONS]: [
        { body: { items: [PHONE, LAPTOP], next_cursor: null } },
        { body: { items: [PHONE], next_cursor: null } },
      ],
      'DELETE /api/v1/auth/sessions/s-laptop': {},
    });
    open();
    const sessions = section(t.sessions.title);
    fireEvent.click(
      await sessions.findByRole('button', { name: t.sessions.revoke('Mac · Chrome') }),
    );
    await waitFor(() => expect(sessions.queryByText('Mac · Chrome')).toBeNull());
    expect(api.count('DELETE /api/v1/auth/sessions/s-laptop')).toBe(1);
  });

  it('this device is ended with "Sign out", not revoke', async () => {
    setup();
    open();
    const sessions = section(t.sessions.title);
    const phone = (await sessions.findByText('iPhone · Safari')).closest('li') as HTMLElement;
    expect(within(phone).queryAllByRole('button')).toHaveLength(0);
  });

  it('a list that fails to load offers a retry', async () => {
    const api = setup({
      [SESSIONS]: [problem(503, 'down'), { body: { items: [PHONE], next_cursor: null } }],
    });
    open();
    fireEvent.click(await screen.findByRole('button', { name: copy.common.retry }));
    expect(await screen.findByText('iPhone · Safari')).toBeDefined();
    expect(api.count(SESSIONS)).toBe(2);
  });

  it('signs out: ends the session and goes to sign-in', async () => {
    const api = setup({ [SIGN_OUT]: {} });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.signOut }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/signin');
    expect(api.count(SIGN_OUT)).toBe(1);
  });
});

describe('passkeys (Ibrahim, 2026-10-08)', () => {
  it('lists passkeys and adds one', async () => {
    const api = setup({
      [ADD_OPTIONS]: { body: { challenge: 'c' } },
      [ADD_VERIFY]: { status: 201, body: { user_id: 'u1', display_name: 'Zee' } },
    });
    open();
    const passkeys = section(t.passkeys.title);
    expect(await passkeys.findByText('iCloud Keychain')).toBeDefined();
    fireEvent.click(passkeys.getByRole('button', { name: t.passkeys.add }));
    await waitFor(() => expect(api.count(ADD_VERIFY)).toBe(1));
    expect(createPasskey).toHaveBeenCalledWith({ challenge: 'c' });
    expect(api.bodies(ADD_VERIFY)).toEqual([{ credential: { id: 'new-credential' } }]);
    await waitFor(() => expect(api.count(PASSKEYS)).toBe(2));
  });

  it('will not remove her last way to sign in', async () => {
    setup({
      [`DELETE /api/v1/auth/passkeys/p-1`]: problem(409, 'This is your last way to sign in.'),
    });
    open();
    const passkeys = section(t.passkeys.title);
    fireEvent.click(
      await passkeys.findByRole('button', { name: t.passkeys.remove('iCloud Keychain') }),
    );
    const confirm = await screen.findByRole('alertdialog', { name: t.passkeys.confirmTitle });
    fireEvent.click(within(confirm).getByRole('button', { name: t.passkeys.confirmRemove }));
    expect(await passkeys.findByText(t.passkeys.lastOne)).toBeDefined();
  });
});

describe('recent authentication (spec 9.2, 12.3)', () => {
  it('asks her to confirm with a passkey, then finishes what she started', async () => {
    const api = setup({
      [ADD_OPTIONS]: [problem(403, REASON.reauthRequired), { body: { challenge: 'c2' } }],
      [ADD_VERIFY]: { status: 201, body: { user_id: 'u1', display_name: 'Zee' } },
      [REAUTH_OPTIONS]: { body: { challenge: 'r' } },
      [REAUTH_VERIFY]: {},
    });
    open();
    fireEvent.click(await section(t.passkeys.title).findByRole('button', { name: t.passkeys.add }));
    const dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    fireEvent.click(within(dialog).getByRole('button', { name: copy.auth.confirm.passkey }));
    await waitFor(() => expect(api.count(ADD_VERIFY)).toBe(1));
    expect(api.bodies(REAUTH_OPTIONS)).toEqual([{ purpose: 'reauth' }]);
    expect(api.bodies(REAUTH_VERIFY)).toEqual([{ credential: { id: 'assertion' } }]);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('a password account confirms with password and code', async () => {
    const api = setup({
      [PASSKEYS]: { body: { items: [], next_cursor: null } },
      [CODES_ROUTE]: [problem(403, REASON.reauthRequired), { body: { recovery_codes: CODES } }],
      [REAUTH_VERIFY]: {},
    });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.codes.regenerate }));
    const dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    expect(within(dialog).queryByRole('button', { name: copy.auth.confirm.passkey })).toBeNull();
    fireEvent.change(within(dialog).getByLabelText(copy.auth.confirm.password), {
      target: { value: 'a long enough passphrase' },
    });
    fireEvent.change(within(dialog).getByLabelText(copy.auth.confirm.code), {
      target: { value: '123456' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: copy.auth.confirm.submit }));
    expect(await screen.findByRole('list', { name: copy.auth.codes.list })).toBeDefined();
    expect(api.bodies(REAUTH_VERIFY)).toEqual([
      { password: 'a long enough passphrase', totp: '123456' },
    ]);
  });

  it('cancelling the confirmation leaves things as they were', async () => {
    const api = setup({ [CODES_ROUTE]: problem(403, REASON.reauthRequired) });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.codes.regenerate }));
    const dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    fireEvent.click(within(dialog).getByRole('button', { name: copy.common.cancel }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.count(CODES_ROUTE)).toBe(1);
  });
});

describe('[AUTH-4] recovery codes: regenerate', () => {
  it('shows the new codes once and says the old ones stop working', async () => {
    const api = setup({ [CODES_ROUTE]: { body: { recovery_codes: CODES } } });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.codes.regenerate }));
    const list = await screen.findByRole('list', { name: copy.auth.codes.list });
    expect(list.querySelectorAll('li')).toHaveLength(10);
    expect(screen.getByText(t.codes.oldStopWorking)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: copy.auth.codes.done }));
    expect(screen.queryByRole('list', { name: copy.auth.codes.list })).toBeNull();
    expect(api.count(CODES_ROUTE)).toBe(1);
  });
});

describe('[AUTH-6] app-lock PIN', () => {
  it('sets a 6-digit PIN', async () => {
    const api = setup({ [APP_LOCK]: {} });
    open();
    const lock = section(t.pin.title);
    fireEvent.change(await lock.findByLabelText(t.pin.new), { target: { value: '123456' } });
    fireEvent.change(lock.getByLabelText(t.pin.repeat), { target: { value: '123456' } });
    fireEvent.click(lock.getByRole('button', { name: t.pin.save }));
    expect(await lock.findByText(t.pin.saved)).toBeDefined();
    expect(api.bodies(APP_LOCK)).toEqual([{ pin: '123456' }]);
  });

  it('refuses a PIN that is not six digits, or does not match', async () => {
    const api = setup({ [APP_LOCK]: {} });
    open();
    const lock = section(t.pin.title);
    fireEvent.change(await lock.findByLabelText(t.pin.new), { target: { value: '12a4' } });
    fireEvent.click(lock.getByRole('button', { name: t.pin.save }));
    expect(await lock.findByText(t.pin.errors.digits)).toBeDefined();
    fireEvent.change(lock.getByLabelText(t.pin.new), { target: { value: '123456' } });
    fireEvent.change(lock.getByLabelText(t.pin.repeat), { target: { value: '654321' } });
    fireEvent.click(lock.getByRole('button', { name: t.pin.save }));
    expect(await lock.findByText(t.pin.errors.match)).toBeDefined();
    expect(api.count(APP_LOCK)).toBe(0);
  });

  it.each(['12345', '1234567'])('refuses a PIN of the wrong length (%s)', async (pin) => {
    const api = setup({ [APP_LOCK]: {} });
    open();
    const lock = section(t.pin.title);
    fireEvent.change(await lock.findByLabelText(t.pin.new), { target: { value: pin } });
    fireEvent.change(lock.getByLabelText(t.pin.repeat), { target: { value: pin } });
    fireEvent.click(lock.getByRole('button', { name: t.pin.save }));
    expect(await lock.findByText(t.pin.errors.digits)).toBeDefined();
    expect(api.count(APP_LOCK)).toBe(0);
  });

  it('removes the PIN after asking, and says so next to the PIN', async () => {
    const api = setup({ [APP_LOCK]: {} });
    open();
    const lock = section(t.pin.title);
    fireEvent.click(await lock.findByRole('button', { name: t.pin.remove }));
    const confirm = await screen.findByRole('alertdialog', { name: t.pin.confirmTitle });
    fireEvent.click(within(confirm).getByRole('button', { name: t.pin.confirmRemove }));
    expect(await lock.findByText(t.pin.removed)).toBeDefined();
    expect(api.bodies(APP_LOCK)).toEqual([{ pin: null }]);
  });

  it('keeping the PIN when asked sends nothing', async () => {
    const api = setup({ [APP_LOCK]: {} });
    open();
    fireEvent.click(await section(t.pin.title).findByRole('button', { name: t.pin.remove }));
    const confirm = await screen.findByRole('alertdialog', { name: t.pin.confirmTitle });
    fireEvent.click(within(confirm).getByRole('button', { name: copy.common.cancel }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(api.count(APP_LOCK)).toBe(0);
  });
});

describe('feedback where it happened', () => {
  it('offline: says it is the connection', async () => {
    setup();
    open();
    const lock = section(t.pin.title);
    fireEvent.change(await lock.findByLabelText(t.pin.new), { target: { value: '123456' } });
    fireEvent.change(lock.getByLabelText(t.pin.repeat), { target: { value: '123456' } });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    fireEvent.click(lock.getByRole('button', { name: t.pin.save }));
    expect(await lock.findByText(copy.common.networkError)).toBeDefined();
  });

  it('only the button that started an action shows it is busy', async () => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    setup({ [CODES_ROUTE]: { body: { recovery_codes: CODES } } });
    open();
    const regenerate = await screen.findByRole('button', { name: t.codes.regenerate });
    const answered = globalThis.fetch;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith('/recovery-codes')) await held;
        return answered(input, init);
      }),
    );
    fireEvent.click(regenerate);
    await waitFor(() => expect(regenerate.getAttribute('aria-busy')).toBe('true'));
    expect(
      screen.getByRole('button', { name: t.passkeys.add }).getAttribute('aria-busy'),
    ).toBeNull();
    expect(screen.getByRole('button', { name: t.pin.save }).getAttribute('aria-busy')).toBeNull();
    release();
    expect(await screen.findByRole('list', { name: copy.auth.codes.list })).toBeDefined();
  });

  it('sign out is a plain action, not a danger one', async () => {
    setup();
    open();
    const signOutButton = await screen.findByRole('button', { name: t.signOut });
    expect(signOutButton.dataset.variant).toBe('secondary');
  });
});

describe('recent authentication: edge cases', () => {
  it('while it is not known whether she has a passkey, both ways are offered', async () => {
    setup({
      [PASSKEYS]: problem(503, 'down'),
      [CODES_ROUTE]: problem(403, REASON.reauthRequired),
    });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.codes.regenerate }));
    const dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    expect(within(dialog).getByRole('button', { name: copy.auth.confirm.passkey })).toBeDefined();
    expect(within(dialog).getByLabelText(copy.auth.confirm.password)).toBeDefined();
  });

  it('a cancelled password is not kept for next time', async () => {
    setup({
      [PASSKEYS]: { body: { items: [], next_cursor: null } },
      [CODES_ROUTE]: problem(403, REASON.reauthRequired),
    });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.codes.regenerate }));
    let dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    fireEvent.change(within(dialog).getByLabelText(copy.auth.confirm.password), {
      target: { value: 'a long enough passphrase' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: copy.common.cancel }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const again = screen.getByRole('button', { name: t.codes.regenerate });
    await waitFor(() => expect(again.getAttribute('aria-busy')).toBeNull());
    fireEvent.click(again);
    dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    expect(
      (within(dialog).getByLabelText(copy.auth.confirm.password) as HTMLInputElement).value,
    ).toBe('');
  });

  it('offline while confirming: says it is the connection', async () => {
    setup({ [CODES_ROUTE]: problem(403, REASON.reauthRequired) });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.codes.regenerate }));
    const dialog = await screen.findByRole('dialog', { name: copy.auth.confirm.title });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    fireEvent.click(within(dialog).getByRole('button', { name: copy.auth.confirm.passkey }));
    expect(await within(dialog).findByText(copy.common.networkError)).toBeDefined();
  });
});

describe('keyboard and screen reader users keep their place (WCAG 2.4.3)', () => {
  it('dismissing a result moves focus to its section heading', async () => {
    setup({ [APP_LOCK]: {} });
    open();
    const lock = section(t.pin.title);
    fireEvent.change(await lock.findByLabelText(t.pin.new), { target: { value: '123456' } });
    fireEvent.change(lock.getByLabelText(t.pin.repeat), { target: { value: '123456' } });
    fireEvent.click(lock.getByRole('button', { name: t.pin.save }));
    await lock.findByText(t.pin.saved);
    fireEvent.click(lock.getByRole('button', { name: copy.common.dismiss }));
    expect(document.activeElement).toBe(lock.getByRole('heading', { name: t.pin.title }));
  });
});

describe('[AUTH-6] lock after (CR-025: spec 11.6 app_lock_timeout_s)', () => {
  it('shows her timeout and saves a new one with PUT /auth/app-lock', async () => {
    const api = setup({ 'PUT /api/v1/auth/app-lock': { status: 204 } });
    open();
    const select = (await screen.findByLabelText(t.lockAfter.label)) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('300'));
    fireEvent.change(select, { target: { value: '900' } });
    expect(await screen.findByText(t.lockAfter.saved)).toBeDefined();
    expect(api.bodies('PUT /api/v1/auth/app-lock')).toEqual([{ timeout_s: 900 }]);
  });
});
