import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { createPasskey, PasskeyCancelled, signWithPasskey } from '../../lib/auth/webauthn';
import { useLockStore } from '../../lib/lock/store';
import { fakeApi, problem } from '../../lib/testing/fakeApi';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { SignInScreen } from './SignInScreen';

vi.mock('../../lib/auth/webauthn', async (original) => ({
  ...(await original<typeof import('../../lib/auth/webauthn')>()),
  createPasskey: vi.fn(),
  signWithPasskey: vi.fn(),
}));

const t = copy.auth.signIn;
const OPTIONS = 'POST /api/v1/auth/signin/options';
const VERIFY = 'POST /api/v1/auth/signin/verify';
const PASSWORD = 'POST /api/v1/auth/signin/password';
const RECOVERY = 'POST /api/v1/auth/signin/recovery';
const ADD_PASSKEY = 'POST /api/v1/auth/passkeys/verify';
const SIGNED_IN = { user_id: 'u1', display_name: 'Zee' };

function open(url = '/signin') {
  return renderRoute(<SignInScreen />, { path: '/signin', url });
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

beforeEach(() => {
  vi.mocked(signWithPasskey).mockResolvedValue({ id: 'assertion' } as never);
  vi.mocked(createPasskey).mockResolvedValue({ id: 'new-credential' } as never);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(signWithPasskey).mockReset();
  vi.mocked(createPasskey).mockReset();
});

describe('[AUTH-2] sign in with a passkey', () => {
  it('signs in with a discoverable passkey (no email needed) and goes to Today', async () => {
    const api = fakeApi({
      [OPTIONS]: { body: { challenge: 'c' } },
      [VERIFY]: { body: SIGNED_IN },
    });
    const { container } = open();
    await expectNoAxeViolations(container);
    expect(screen.queryByLabelText(t.email)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
    expect(api.bodies(OPTIONS)).toEqual([{}]);
    expect(signWithPasskey).toHaveBeenCalledWith({ challenge: 'c' });
    expect(api.bodies(VERIFY)).toEqual([{ credential: { id: 'assertion' } }]);
  });

  it('returns to the page she was sent from', async () => {
    fakeApi({ [OPTIONS]: { body: { challenge: 'c' } }, [VERIFY]: { body: SIGNED_IN } });
    open('/signin?next=%2Fsettings%2Fsecurity');
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/settings/security');
  });

  it.each(['//evil.example/x', '/\\evil.example/x', '/\t/evil.example', 'https://evil.example/'])(
    'never returns to another site (%s)',
    async (next) => {
      fakeApi({ [OPTIONS]: { body: { challenge: 'c' } }, [VERIFY]: { body: SIGNED_IN } });
      open(`/signin?next=${encodeURIComponent(next)}`);
      fireEvent.click(screen.getByRole('button', { name: t.passkey }));
      expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
    },
  );

  it('[AUTH-6] signing in starts unlocked, even if an old lock was left behind', async () => {
    fakeApi({ [OPTIONS]: { body: { challenge: 'c' } }, [VERIFY]: { body: SIGNED_IN } });
    useLockStore.setState({ locked: true, covered: false });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    await screen.findByTestId('arrived');
    expect(useLockStore.getState().locked).toBe(false);
  });

  it('a refused passkey says it did not work', async () => {
    fakeApi({ [OPTIONS]: { body: { challenge: 'c' } }, [VERIFY]: problem(401, 'Sign-in failed.') });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    expect(await screen.findByText(t.failed)).toBeDefined();
  });

  it('a dismissed prompt says so', async () => {
    vi.mocked(signWithPasskey).mockRejectedValue(new PasskeyCancelled());
    const api = fakeApi({ [OPTIONS]: { body: { challenge: 'c' } } });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    expect(await screen.findByText(t.cancelled)).toBeDefined();
    expect(api.count(VERIFY)).toBe(0);
  });

  it('[AUTH-7] after too many failures it says how long to wait', async () => {
    fakeApi({
      [OPTIONS]: { body: { challenge: 'c' } },
      [VERIFY]: problem(429, 'Too many failed sign-ins. Try again later.', {
        'Retry-After': '840',
      }),
    });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    expect(await screen.findByText(t.locked(14))).toBeDefined();
  });
});

describe('[AUTH-3] sign in with password and authenticator code', () => {
  it('sends email, password and code, then goes to Today', async () => {
    const api = fakeApi({ [PASSWORD]: { body: SIGNED_IN } });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.usePassword }));
    type(t.email, 'zee@example.test');
    type(t.password, 'a long enough passphrase');
    type(t.code, '123456');
    fireEvent.click(screen.getByRole('button', { name: t.submit }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
    expect(api.bodies(PASSWORD)).toEqual([
      { email: 'zee@example.test', password: 'a long enough passphrase', totp: '123456' },
    ]);
  });

  it('checks the fields first', async () => {
    const api = fakeApi({});
    open();
    fireEvent.click(screen.getByRole('button', { name: t.usePassword }));
    fireEvent.click(screen.getByRole('button', { name: t.submit }));
    expect(await screen.findByText(t.errors.email)).toBeDefined();
    expect(screen.getByText(t.errors.password)).toBeDefined();
    expect(screen.getByText(t.errors.code)).toBeDefined();
    expect(api.count(PASSWORD)).toBe(0);
  });

  it('a wrong password or code gives one message that does not say which', async () => {
    fakeApi({ [PASSWORD]: problem(401, 'Sign-in failed.') });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.usePassword }));
    type(t.email, 'zee@example.test');
    type(t.password, 'a long enough passphrase');
    type(t.code, '123456');
    fireEvent.click(screen.getByRole('button', { name: t.submit }));
    expect(await screen.findByText(t.failed)).toBeDefined();
  });

  it('can go back to the passkey', () => {
    fakeApi({});
    open();
    fireEvent.click(screen.getByRole('button', { name: t.usePassword }));
    fireEvent.click(screen.getByRole('button', { name: t.back }));
    expect(screen.getByRole('button', { name: t.passkey })).toBeDefined();
  });
});

describe('[AUTH-4] sign in with a recovery code (forces a new passkey, CR-013)', () => {
  it('spends the code, creates a new passkey, then signs in', async () => {
    const options = { challenge: 'new' };
    const api = fakeApi({
      [RECOVERY]: { body: { next: 'add_passkey', options } },
      [ADD_PASSKEY]: { status: 201, body: SIGNED_IN },
    });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.useRecoveryCode }));
    type(t.email, 'zee@example.test');
    type(t.recoveryCode, 'abcd-efgh-1');
    fireEvent.click(screen.getByRole('button', { name: t.recoverySubmit }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
    expect(api.bodies(RECOVERY)).toEqual([{ email: 'zee@example.test', code: 'abcd-efgh-1' }]);
    expect(createPasskey).toHaveBeenCalledWith(options);
    expect(api.bodies(ADD_PASSKEY)).toEqual([{ credential: { id: 'new-credential' } }]);
  });

  it('if the new passkey is not created, says the code is spent and how to continue', async () => {
    vi.mocked(createPasskey).mockRejectedValue(new PasskeyCancelled());
    fakeApi({ [RECOVERY]: { body: { next: 'add_passkey', options: { challenge: 'new' } } } });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.useRecoveryCode }));
    type(t.email, 'zee@example.test');
    type(t.recoveryCode, 'abcd-efgh-1');
    fireEvent.click(screen.getByRole('button', { name: t.recoverySubmit }));
    expect(await screen.findByText(t.recoveryPasskeyMissing)).toBeDefined();
  });

  it('a wrong code says it did not work', async () => {
    fakeApi({ [RECOVERY]: problem(401, 'Sign-in failed.') });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.useRecoveryCode }));
    type(t.email, 'zee@example.test');
    type(t.recoveryCode, 'nope');
    fireEvent.click(screen.getByRole('button', { name: t.recoverySubmit }));
    expect(await screen.findByText(t.failed)).toBeDefined();
  });
});

describe('[AUTH-4] recovery: a spent code is reported as spent', () => {
  it('when saving the new passkey fails, says the code is used rather than wrong', async () => {
    fakeApi({
      [RECOVERY]: { body: { next: 'add_passkey', options: { challenge: 'new' } } },
      [ADD_PASSKEY]: problem(400, 'The passkey could not be verified.'),
    });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.useRecoveryCode }));
    type(t.email, 'zee@example.test');
    type(t.recoveryCode, 'abcd-efgh-1');
    fireEvent.click(screen.getByRole('button', { name: t.recoverySubmit }));
    expect(await screen.findByText(t.recoveryPasskeyMissing)).toBeDefined();
  });
});

describe('keyboard and screen reader users keep their place (WCAG 2.4.3)', () => {
  it('switching to password or recovery code moves focus to the heading', () => {
    fakeApi({});
    open();
    const usePassword = screen.getByRole('button', { name: t.usePassword });
    usePassword.focus();
    fireEvent.click(usePassword);
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: t.title }));
    const back = screen.getByRole('button', { name: t.back });
    back.focus();
    fireEvent.click(back);
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: t.title }));
  });

  it('dismissing a message moves focus to the heading, not the page', async () => {
    fakeApi({ [OPTIONS]: { body: { challenge: 'c' } }, [VERIFY]: problem(401, 'Sign-in failed.') });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.passkey }));
    await screen.findByText(t.failed);
    fireEvent.click(screen.getByRole('button', { name: copy.common.dismiss }));
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: t.title }));
  });
});
