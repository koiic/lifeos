import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { createPasskey, PasskeyCancelled } from '../../lib/auth/webauthn';
import { fakeApi, problem } from '../../lib/testing/fakeApi';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { RegisterScreen } from './RegisterScreen';

vi.mock('../../lib/auth/webauthn', async (original) => ({
  ...(await original<typeof import('../../lib/auth/webauthn')>()),
  createPasskey: vi.fn(),
}));

const t = copy.auth.register;
const VERIFY_INVITE = 'POST /api/v1/auth/invites/verify';
const OPTIONS = 'POST /api/v1/auth/register/options';
const VERIFY = 'POST /api/v1/auth/register/verify';
const PASSWORD = 'POST /api/v1/auth/register/password';
const CONFIRM = 'POST /api/v1/auth/totp/confirm';
const CODES = Array.from({ length: 10 }, (_, i) => `abcd-efgh-${String(i)}`);
const URI = 'otpauth://totp/Life%20OS:zee%40example.test?secret=JBSWY3DPEHPK3PXP&issuer=Life%20OS';

function open(url = '/register?token=tok-1') {
  return renderRoute(<RegisterScreen />, { path: '/register', url });
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

beforeEach(() => {
  vi.mocked(createPasskey).mockResolvedValue({ id: 'new-credential' } as never);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(createPasskey).mockReset();
});

describe('[AUTH-1] register: invite only', () => {
  it('an invalid or used invite shows why, and no form', async () => {
    const api = fakeApi({ [VERIFY_INVITE]: { body: { valid: false } } });
    open();
    expect(await screen.findByText(t.invalidTitle)).toBeDefined();
    expect(api.bodies(VERIFY_INVITE)).toEqual([{ token: 'tok-1' }]);
    expect(screen.queryByLabelText(t.name)).toBeNull();
  });

  it('without a token it does not ask the server', async () => {
    const api = fakeApi({});
    open('/register');
    expect(await screen.findByText(t.invalidTitle)).toBeDefined();
    expect(api.count(VERIFY_INVITE)).toBe(0);
  });

  it('an invite the server refuses mid-way (403) shows the invalid state', async () => {
    fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [OPTIONS]: problem(403, 'The invite is not valid.'),
    });
    open();
    await screen.findByLabelText(t.name);
    type(t.name, 'Zee');
    type(t.email, 'zee@example.test');
    fireEvent.click(await screen.findByRole('button', { name: t.createPasskey }));
    expect(await screen.findByText(t.invalidTitle)).toBeDefined();
  });

  it('a network failure while checking offers a retry', async () => {
    const api = fakeApi({ [VERIFY_INVITE]: [problem(503, 'down'), { body: { valid: true } }] });
    open();
    fireEvent.click(await screen.findByRole('button', { name: copy.common.retry }));
    expect(await screen.findByLabelText(t.name)).toBeDefined();
    expect(api.count(VERIFY_INVITE)).toBe(2);
  });
});

describe('[AUTH-2] [AUTH-4] register with a passkey', () => {
  it('creates the passkey, then shows the recovery codes once, then the install guide', async () => {
    const options = { challenge: 'c', rp: { id: 'localhost' } };
    const api = fakeApi({
      [VERIFY_INVITE]: { body: { valid: true, email: 'zee@example.test' } },
      [OPTIONS]: { body: options },
      [VERIFY]: {
        status: 201,
        body: { user_id: 'u1', display_name: 'Zee', recovery_codes: CODES },
      },
    });
    const { container } = open();
    const email = (await screen.findByLabelText(t.email)) as HTMLInputElement;
    expect(email.value).toBe('zee@example.test');
    await expectNoAxeViolations(container);
    type(t.name, 'Zee');
    fireEvent.click(screen.getByRole('button', { name: t.createPasskey }));

    const list = await screen.findByRole('list', { name: copy.auth.codes.list });
    expect(list.querySelectorAll('li')).toHaveLength(10);
    expect(createPasskey).toHaveBeenCalledWith(options);
    expect(api.bodies(OPTIONS)).toEqual([
      { token: 'tok-1', name: 'Zee', email: 'zee@example.test' },
    ]);
    expect(api.bodies(VERIFY)).toEqual([
      {
        token: 'tok-1',
        name: 'Zee',
        email: 'zee@example.test',
        credential: { id: 'new-credential' },
      },
    ]);

    // [ONB-1] J1 step 3: in a browser tab, the install guide comes next.
    fireEvent.click(screen.getByRole('button', { name: copy.auth.codes.done }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/install');
  });

  it.each(['installed', 'dismissed'] as const)(
    '[ONB-1] guide already %s: straight to Today',
    async (state) => {
      if (state === 'installed') {
        window.matchMedia = ((query: string) => ({
          matches: query === '(display-mode: standalone)',
          media: query,
        })) as unknown as typeof window.matchMedia;
      } else {
        localStorage.setItem('lifeos.installDismissed', '1');
      }
      try {
        fakeApi({
          [VERIFY_INVITE]: { body: { valid: true, email: 'zee@example.test' } },
          [OPTIONS]: { body: { challenge: 'c' } },
          [VERIFY]: {
            status: 201,
            body: { user_id: 'u1', display_name: 'Zee', recovery_codes: CODES },
          },
        });
        open();
        await screen.findByLabelText(t.name);
        type(t.name, 'Zee');
        fireEvent.click(screen.getByRole('button', { name: t.createPasskey }));
        fireEvent.click(await screen.findByRole('button', { name: copy.auth.codes.done }));
        expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
      } finally {
        Reflect.deleteProperty(window, 'matchMedia');
        localStorage.clear();
      }
    },
  );

  it('checks the name and email before asking the server', async () => {
    const api = fakeApi({ [VERIFY_INVITE]: { body: { valid: true } } });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.createPasskey }));
    expect(await screen.findByText(t.errors.name)).toBeDefined();
    type(t.name, 'Zee');
    type(t.email, 'not-an-email');
    fireEvent.click(screen.getByRole('button', { name: t.createPasskey }));
    expect(await screen.findByText(t.errors.email)).toBeDefined();
    expect(api.count(OPTIONS)).toBe(0);
  });

  it('an email that already has an account is marked on the email field', async () => {
    fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [OPTIONS]: problem(409, 'This email address already has an account.'),
    });
    open();
    await screen.findByLabelText(t.name);
    type(t.name, 'Zee');
    type(t.email, 'zee@example.test');
    fireEvent.click(await screen.findByRole('button', { name: t.createPasskey }));
    await waitFor(() =>
      expect(screen.getByLabelText(t.email).getAttribute('aria-invalid')).toBe('true'),
    );
    expect(screen.getByText(t.errors.emailInUse)).toBeDefined();
  });

  it('a dismissed passkey prompt says so and keeps the form', async () => {
    vi.mocked(createPasskey).mockRejectedValue(new PasskeyCancelled());
    const api = fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [OPTIONS]: { body: { challenge: 'c' } },
    });
    open();
    await screen.findByLabelText(t.name);
    type(t.name, 'Zee');
    type(t.email, 'zee@example.test');
    fireEvent.click(await screen.findByRole('button', { name: t.createPasskey }));
    expect(await screen.findByText(t.errors.passkeyCancelled)).toBeDefined();
    expect(api.count(VERIFY)).toBe(0);
    expect(screen.getByRole('button', { name: t.createPasskey })).toBeDefined();
  });
});

describe('[AUTH-3] [AUTH-4] register with a password and an authenticator app', () => {
  async function toPasswordStep(api = fakeApi({ [VERIFY_INVITE]: { body: { valid: true } } })) {
    open();
    await screen.findByLabelText(t.name);
    type(t.name, 'Zee');
    type(t.email, 'zee@example.test');
    fireEvent.click(await screen.findByRole('button', { name: t.usePassword }));
    await screen.findByLabelText(t.password);
    return api;
  }

  it('needs at least 12 characters', async () => {
    const api = await toPasswordStep();
    type(t.password, 'short');
    fireEvent.click(screen.getByRole('button', { name: t.continue }));
    expect(await screen.findByText(t.errors.passwordShort)).toBeDefined();
    expect(api.count(PASSWORD)).toBe(0);
  });

  it('shows the server message for a too-common password', async () => {
    const api = fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [PASSWORD]: {
        status: 422,
        headers: { 'Content-Type': 'application/problem+json' },
        body: {
          title: 'Unprocessable',
          detail: 'Invalid request',
          errors: [
            {
              field: 'password',
              code: 'password_too_common',
              message: 'This password is too common.',
            },
          ],
        },
      },
    });
    await toPasswordStep(api);
    type(t.password, 'correcthorse1');
    fireEvent.click(screen.getByRole('button', { name: t.continue }));
    expect(await screen.findByText(t.errors.passwordCommon)).toBeDefined();
  });

  it('sets up the authenticator app, confirms a code, then shows the recovery codes', async () => {
    const api = fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [PASSWORD]: {
        status: 201,
        body: { user_id: 'u1', display_name: 'Zee', provisioning_uri: URI },
      },
      [CONFIRM]: [problem(401, 'Sign-in failed.'), { body: { recovery_codes: CODES } }],
    });
    await toPasswordStep(api);
    type(t.password, 'a long enough passphrase');
    fireEvent.click(screen.getByRole('button', { name: t.continue }));

    const link = await screen.findByRole('link', { name: t.openAuthenticator });
    expect(link.getAttribute('href')).toBe(URI);
    expect(screen.getByText('JBSW Y3DP EHPK 3PXP')).toBeDefined();
    expect(api.bodies(PASSWORD)).toEqual([
      {
        token: 'tok-1',
        name: 'Zee',
        email: 'zee@example.test',
        password: 'a long enough passphrase',
      },
    ]);

    type(t.code, '000000');
    fireEvent.click(screen.getByRole('button', { name: t.confirm }));
    expect(await screen.findByText(t.errors.codeWrong)).toBeDefined();

    type(t.code, '123456');
    fireEvent.click(screen.getByRole('button', { name: t.confirm }));
    expect(await screen.findByRole('list', { name: copy.auth.codes.list })).toBeDefined();
    expect(api.bodies(CONFIRM)).toEqual([{ code: '000000' }, { code: '123456' }]);
  });

  it('a code must be six digits', async () => {
    const api = fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [PASSWORD]: {
        status: 201,
        body: { user_id: 'u1', display_name: 'Zee', provisioning_uri: URI },
      },
    });
    await toPasswordStep(api);
    type(t.password, 'a long enough passphrase');
    fireEvent.click(screen.getByRole('button', { name: t.continue }));
    await screen.findByLabelText(t.code);
    type(t.code, '12ab');
    fireEvent.click(screen.getByRole('button', { name: t.confirm }));
    expect(await screen.findByText(t.errors.code)).toBeDefined();
    expect(api.count(CONFIRM)).toBe(0);
  });

  it('back from a reload before confirming: asks for the code only (CR-014)', async () => {
    const api = fakeApi({ [CONFIRM]: { body: { recovery_codes: CODES } } });
    open('/register?step=confirm');
    await screen.findByLabelText(t.code);
    type(t.code, '123456');
    fireEvent.click(screen.getByRole('button', { name: t.confirm }));
    expect(await screen.findByRole('list', { name: copy.auth.codes.list })).toBeDefined();
    expect(api.count(VERIFY_INVITE)).toBe(0);
  });
});

describe('[AUTH-3] the authenticator link is only ever an otpauth link', () => {
  it('anything else from the server is not shown as a link', async () => {
    fakeApi({
      [VERIFY_INVITE]: { body: { valid: true } },
      [PASSWORD]: {
        status: 201,
        body: { user_id: 'u1', display_name: 'Zee', provisioning_uri: 'javascript:alert(1)' },
      },
    });
    open();
    await screen.findByLabelText(t.name);
    type(t.name, 'Zee');
    type(t.email, 'zee@example.test');
    fireEvent.click(screen.getByRole('button', { name: t.usePassword }));
    await screen.findByLabelText(t.password);
    type(t.password, 'a long enough passphrase');
    fireEvent.click(screen.getByRole('button', { name: t.continue }));
    expect(await screen.findByText(copy.common.networkError)).toBeDefined();
    expect(screen.queryByRole('link')).toBeNull();
  });
});

describe('keyboard and screen reader users keep their place (WCAG 2.4.3)', () => {
  it('each new step moves focus to its heading', async () => {
    fakeApi({ [VERIFY_INVITE]: { body: { valid: true } } });
    open();
    await screen.findByLabelText(t.name);
    type(t.name, 'Zee');
    type(t.email, 'zee@example.test');
    // A real click focuses the button first; focus must then move to the new step's heading.
    const usePassword = screen.getByRole('button', { name: t.usePassword });
    usePassword.focus();
    fireEvent.click(usePassword);
    const heading = await screen.findByRole('heading', { name: t.passwordTitle });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    const back = screen.getByRole('button', { name: copy.common.back });
    back.focus();
    fireEvent.click(back);
    const first = await screen.findByRole('heading', { name: t.title });
    await waitFor(() => expect(document.activeElement).toBe(first));
  });
});
