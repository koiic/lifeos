import { useQuery, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { copy } from '../copy/en-GB';
import { api } from '../lib/api';
import { hasReason, REASON, signOut } from '../lib/auth/session';
import { PasskeyCancelled, signWithPasskey } from '../lib/auth/webauthn';
import { DEFAULT_LOCK_TIMEOUT_S } from '../lib/lock/rules';
import { useLockStore } from '../lib/lock/store';
import { meQuery } from '../lib/me/me';
import { startLockWatch } from '../lib/lock/watch';
import { LockScreen } from '../ui/LockScreen';

const t = copy.lock;

/**
 * AUTH-6, spec 11.6: around the signed-in app. Watches the time spent in the background; when
 * locked, only the lock screen renders (none of her data) until she unlocks with a passkey
 * (`/auth/reauth`, purpose `unlock`) or her PIN (`/auth/app-lock/unlock`). While the app is in
 * the background it is covered, so the app switcher snapshot shows the lock state.
 */
export function AppLock({ children }: { children: ReactNode }) {
  const locked = useLockStore((state) => state.locked);
  const covered = useLockStore((state) => state.covered);
  const unlock = useLockStore((state) => state.unlock);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const app = useRef<HTMLDivElement>(null);

  // Covered: the app behind the cover cannot be reached by keyboard or assistive technology.
  // (React 18's types have no `inert` prop, so the attribute is set on the element.)
  useEffect(() => {
    app.current?.toggleAttribute('inert', covered);
  }, [covered, locked]);

  // Her timeout from GET /me (CR-025); the spec default until it loads. /me is not fetched
  // while locked (nothing of hers loads behind the lock screen).
  const me = useQuery({ ...meQuery, enabled: !locked });
  const timeoutS = me.data?.settings.app_lock_timeout_s ?? DEFAULT_LOCK_TIMEOUT_S;
  useEffect(() => startLockWatch({ timeoutS }), [timeoutS]);

  const passkeys = useQuery({
    queryKey: ['passkeys'],
    queryFn: () => api.request('GET', '/api/v1/auth/passkeys'),
    enabled: locked,
  });

  const leave = async () => {
    await signOut(queryClient);
    navigate('/signin', { replace: true });
  };

  const attempt = async (verify: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await verify();
      unlock();
    } catch (failure) {
      if (hasReason(failure, 401, REASON.pinLockedOut)) {
        await leave();
        return;
      }
      if (failure instanceof PasskeyCancelled) return;
      setError(
        hasReason(failure, 401, REASON.wrongPin)
          ? t.wrongPin
          : hasReason(failure, 409, REASON.noPin)
            ? t.noPin
            : failure instanceof TypeError
              ? copy.common.networkError
              : t.failed,
      );
    } finally {
      setBusy(false);
    }
  };

  const withPasskey = () =>
    attempt(async () => {
      const options = await api.request('POST', '/api/v1/auth/reauth/options', {
        purpose: 'unlock',
      });
      const credential = await signWithPasskey(options);
      await api.request('POST', '/api/v1/auth/reauth/verify', { credential });
    });

  const withPin = (pin: string) =>
    attempt(async () => {
      await api.request('POST', '/api/v1/auth/app-lock/unlock', { pin });
    });

  if (locked) {
    // Offered unless she is known to have none (a list that failed must not leave her stuck).
    const hasPasskey = !(passkeys.isSuccess && passkeys.data.items.length === 0);
    return (
      <LockScreen
        title={t.title}
        {...(hasPasskey
          ? { passkey: { label: t.passkey, onUnlock: () => void withPasskey(), busy } }
          : {})}
        pin={{
          label: t.pin,
          submitLabel: t.unlock,
          onSubmit: (pin) => void withPin(pin),
          invalidMessage: t.pinInvalid,
          busy,
          ...(error === null ? {} : { error }),
        }}
        signOut={{ label: t.signOut, onClick: () => void leave() }}
      />
    );
  }

  return (
    <>
      <div ref={app}>{children}</div>
      {covered && <LockScreen title={t.title} />}
    </>
  );
}
