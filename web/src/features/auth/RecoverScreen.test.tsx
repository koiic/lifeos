import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { createPasskey } from '../../lib/auth/webauthn';
import { fakeApi, problem } from '../../lib/testing/fakeApi';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { RecoverScreen } from './RecoverScreen';

vi.mock('../../lib/auth/webauthn', async (original) => ({
  ...(await original<typeof import('../../lib/auth/webauthn')>()),
  createPasskey: vi.fn(),
}));

const t = copy.auth.recover;
const OPTIONS = 'POST /api/v1/auth/recover/options';
const VERIFY = 'POST /api/v1/auth/recover/verify';
const CODES = Array.from({ length: 10 }, (_, i) => `abcd-efgh-${String(i)}`);

function open(url = '/recover?token=rec-1') {
  return renderRoute(<RecoverScreen />, { path: '/recover', url });
}

beforeEach(() => {
  vi.mocked(createPasskey).mockResolvedValue({ id: 'new-credential' } as never);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(createPasskey).mockReset();
});

describe('[AUTH-8] recovery invite: a new passkey on her existing account', () => {
  it('creates the passkey, shows fresh recovery codes, then goes to Today', async () => {
    const api = fakeApi({
      [OPTIONS]: { body: { challenge: 'c' } },
      [VERIFY]: {
        status: 201,
        body: { user_id: 'u1', display_name: 'Zee', recovery_codes: CODES },
      },
    });
    const { container } = open();
    await expectNoAxeViolations(container);
    fireEvent.click(screen.getByRole('button', { name: t.createPasskey }));
    expect(await screen.findByRole('list', { name: copy.auth.codes.list })).toBeDefined();
    expect(api.bodies(OPTIONS)).toEqual([{ token: 'rec-1' }]);
    expect(api.bodies(VERIFY)).toEqual([{ token: 'rec-1', credential: { id: 'new-credential' } }]);
    fireEvent.click(screen.getByRole('button', { name: copy.auth.codes.done }));
    expect((await screen.findByTestId('arrived')).textContent).toBe('/today');
  });

  it('an invalid or expired recovery link shows why', async () => {
    fakeApi({ [OPTIONS]: problem(403, 'The invite is not valid.') });
    open();
    fireEvent.click(screen.getByRole('button', { name: t.createPasskey }));
    expect(await screen.findByText(t.invalidTitle)).toBeDefined();
  });

  it('without a token there is nothing to do', () => {
    fakeApi({});
    open('/recover');
    expect(screen.getByText(t.invalidTitle)).toBeDefined();
    expect(screen.queryByRole('button', { name: t.createPasskey })).toBeNull();
  });
});
