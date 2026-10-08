import { useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { copy } from '../../copy/en-GB';
import { api } from '../../lib/api';
import { startSession } from '../../lib/auth/session';
import { createPasskey, signWithPasskey } from '../../lib/auth/webauthn';
import { bindField } from '../../lib/forms/bindField';
import { zodResolver } from '../../lib/forms/zodResolver';
import { Button } from '../../ui/Button';
import { Stack } from '../../ui/Stack';
import { TextField } from '../../ui/TextField';
import { AuthPage, failureMessage, Notice } from './parts';

const t = copy.auth.signIn;

const email = z.string().trim().min(1, t.errors.email);
const passwordSchema = z.object({
  email,
  password: z.string().min(1, t.errors.password),
  totp: z.string().regex(/^\d{6}$/, t.errors.code),
});
const recoverySchema = z.object({
  email,
  code: z.string().trim().min(1, t.errors.recoveryCode),
});

type Mode = 'passkey' | 'password' | 'recovery';

/**
 * Where to go after signing in: a path on this site only. Resolved as the browser would (so
 * `//host`, `/\\host` and the like count as other sites), and nothing with control characters.
 */
function safeNext(next: string | null): string {
  const unsafe = (char: string) => char === '\\' || char.charCodeAt(0) < 0x20;
  if (next === null || !next.startsWith('/') || [...next].some(unsafe)) return '/today';
  const url = new URL(next, window.location.origin);
  return url.origin === window.location.origin
    ? `${url.pathname}${url.search}${url.hash}`
    : '/today';
}

/**
 * Spec 5.2 "Sign in": a discoverable passkey (AUTH-2, no email needed); "Use password" with the
 * authenticator code (AUTH-3); "Use recovery code", which makes a new passkey before the session
 * starts (AUTH-4, CR-013). A lockout says how long to wait (AUTH-7).
 */
export function SignInScreen() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>('passkey');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(0);

  const password = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { email: '', password: '', totp: '' },
  });
  const recovery = useForm<z.infer<typeof recoverySchema>>({
    resolver: zodResolver(recoverySchema),
    defaultValues: { email: '', code: '' },
  });

  const signedIn = () => {
    startSession(queryClient);
    navigate(safeNext(params.get('next')), { replace: true });
  };

  const act = async (
    work: () => Promise<void>,
    messages: { cancelled: string; passkeyFailed: string } = {
      cancelled: t.cancelled,
      passkeyFailed: t.failed,
    },
  ) => {
    setBusy(true);
    setNotice(null);
    try {
      await work();
      signedIn();
    } catch (error) {
      setNotice(failureMessage(error, messages));
    } finally {
      setBusy(false);
    }
  };

  const withPasskey = () =>
    act(async () => {
      const options = await api.request('POST', '/api/v1/auth/signin/options', {});
      const credential = await signWithPasskey(options);
      await api.request('POST', '/api/v1/auth/signin/verify', { credential });
    });

  const withPassword = password.handleSubmit((values) =>
    act(async () => {
      await api.request('POST', '/api/v1/auth/signin/password', {
        email: values.email,
        password: values.password,
        totp: values.totp,
      });
    }),
  );

  // The code is spent once the server accepts it; a new passkey then starts the session.
  const withRecoveryCode = recovery.handleSubmit((values) =>
    act(
      async () => {
        const recovered = await api.request('POST', '/api/v1/auth/signin/recovery', {
          email: values.email,
          code: values.code,
        });
        try {
          const credential = await createPasskey(recovered.options);
          await api.request('POST', '/api/v1/auth/passkeys/verify', { credential });
        } catch {
          // Whatever stopped the new passkey, the code is spent: say so (not "wrong code").
          throw new Error('recovery passkey not created');
        }
      },
      { cancelled: t.recoveryPasskeyMissing, passkeyFailed: t.recoveryPasskeyMissing },
    ),
  );

  const switchTo = (next: Mode) => {
    setNotice(null);
    setMode(next);
  };

  return (
    <AuthPage title={t.title} intro={t.intro} focusKey={`${mode}:${String(dismissed)}`}>
      <Notice
        message={notice}
        onDismiss={() => {
          setNotice(null);
          setDismissed((n) => n + 1);
        }}
      />
      {mode === 'passkey' && (
        <Stack gap={3}>
          <Button icon="key" busy={busy} onClick={() => void withPasskey()}>
            {t.passkey}
          </Button>
          <Button variant="ghost" onClick={() => switchTo('password')}>
            {t.usePassword}
          </Button>
          <Button variant="ghost" onClick={() => switchTo('recovery')}>
            {t.useRecoveryCode}
          </Button>
        </Stack>
      )}
      {mode === 'password' && (
        <form noValidate onSubmit={(event: FormEvent) => void withPassword(event)}>
          <Stack gap={4}>
            <TextField
              label={t.email}
              type="email"
              autoComplete="username"
              {...bindField(password, 'email')}
            />
            <TextField
              label={t.password}
              type="password"
              autoComplete="current-password"
              {...bindField(password, 'password')}
            />
            <TextField
              label={t.code}
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              {...bindField(password, 'totp')}
            />
            <Button type="submit" busy={busy}>
              {t.submit}
            </Button>
            <Button variant="ghost" onClick={() => switchTo('passkey')}>
              {t.back}
            </Button>
          </Stack>
        </form>
      )}
      {mode === 'recovery' && (
        <form noValidate onSubmit={(event: FormEvent) => void withRecoveryCode(event)}>
          <Stack gap={4}>
            <TextField
              label={t.email}
              type="email"
              autoComplete="username"
              {...bindField(recovery, 'email')}
            />
            <TextField
              label={t.recoveryCode}
              hint={t.recoveryHint}
              autoComplete="off"
              {...bindField(recovery, 'code')}
            />
            <Button type="submit" busy={busy}>
              {t.recoverySubmit}
            </Button>
            <Button variant="ghost" onClick={() => switchTo('passkey')}>
              {t.back}
            </Button>
          </Stack>
        </form>
      )}
    </AuthPage>
  );
}
