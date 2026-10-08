import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import { api, ApiError } from '../../lib/api';
import { startSession } from '../../lib/auth/session';
import { createPasskey } from '../../lib/auth/webauthn';
import { Button } from '../../ui/Button';
import { ErrorState } from '../../ui/ErrorState';
import { AuthPage, failureMessage, Notice, RecoveryCodesStep } from './parts';

const t = copy.auth.recover;

/**
 * AUTH-8 (spec 9.2): the recovery invite Ibrahim issues leads here. A new passkey is registered
 * on her existing account; fresh recovery codes are shown once and the old ones stop working.
 */
export function RecoverScreen() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [invalid, setInvalid] = useState(token === '');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(0);
  const dismiss = () => {
    setNotice(null);
    setDismissed((n) => n + 1);
  };

  const recover = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const options = await api.request('POST', '/api/v1/auth/recover/options', { token });
      const credential = await createPasskey(options);
      const registered = await api.request('POST', '/api/v1/auth/recover/verify', {
        token,
        credential,
      });
      setCodes(registered.recovery_codes);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) setInvalid(true);
      else setNotice(failureMessage(error, { cancelled: t.cancelled, passkeyFailed: t.cancelled }));
    } finally {
      setBusy(false);
    }
  };

  if (codes !== null) {
    return (
      <RecoveryCodesStep
        codes={codes}
        onDone={() => {
          startSession(queryClient);
          navigate('/today', { replace: true });
        }}
      />
    );
  }

  if (invalid) {
    return (
      <AuthPage focusKey={String(dismissed)} title={t.title}>
        <ErrorState title={t.invalidTitle} body={t.invalidBody} />
      </AuthPage>
    );
  }

  return (
    <AuthPage focusKey={String(dismissed)} title={t.title} intro={t.body}>
      <Notice message={notice} onDismiss={dismiss} />
      <Button icon="key" busy={busy} onClick={() => void recover()}>
        {t.createPasskey}
      </Button>
    </AuthPage>
  );
}
