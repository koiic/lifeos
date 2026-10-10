import { useQuery, useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { copy } from '../../copy/en-GB';
import { api, ApiError } from '../../lib/api';
import { adoptDeviceTimezone } from '../../lib/me/me';
import { startSession } from '../../lib/auth/session';
import { needsInstallGuide } from '../../lib/install/install';
import { createPasskey } from '../../lib/auth/webauthn';
import { bindField } from '../../lib/forms/bindField';
import { zodResolver } from '../../lib/forms/zodResolver';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import { TextField } from '../../ui/TextField';
import { AuthPage, failureMessage, Notice, RecoveryCodesStep } from './parts';

const t = copy.auth.register;

const detailsSchema = z.object({
  name: z.string().trim().min(1, t.errors.name).max(100, t.errors.name),
  email: z
    .string()
    .trim()
    .regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, t.errors.email),
});
type Details = z.infer<typeof detailsSchema>;

const passwordSchema = z.object({ password: z.string().min(12, t.errors.passwordShort) });
const codeSchema = z.object({ code: z.string().regex(/^\d{6}$/, t.errors.code) });

type Step =
  | { kind: 'details' }
  | { kind: 'password' }
  | { kind: 'totp'; uri: string | null }
  | { kind: 'codes'; codes: string[] }
  | { kind: 'invalid' };

/** The key in an otpauth:// URI, in groups of four for typing (spec 12.3: RFC 6238). */
function secretOf(uri: string): string {
  const secret = new URL(uri).searchParams.get('secret') ?? '';
  return secret.match(/.{1,4}/g)?.join(' ') ?? '';
}

/**
 * Spec 5.2 "Register (invite)": J1 step 2. A valid invite (AUTH-1) → name and email → a passkey
 * (AUTH-2), or a password and an authenticator app (AUTH-3, CR-014) → recovery codes (AUTH-4).
 * `?step=confirm`: back to the authenticator code after a reload (the session exists, inactive).
 */
export function RegisterScreen() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const confirming = params.get('step') === 'confirm';
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<Step>(
    confirming
      ? { kind: 'totp', uri: null }
      : token === ''
        ? { kind: 'invalid' }
        : { kind: 'details' },
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(0);
  const dismiss = () => {
    setNotice(null);
    setDismissed((n) => n + 1);
  };

  const invite = useQuery({
    queryKey: ['invite', token],
    queryFn: () => api.request('POST', '/api/v1/auth/invites/verify', { token }),
    enabled: token !== '' && !confirming,
    staleTime: Infinity,
  });

  const details = useForm<Details>({
    resolver: zodResolver(detailsSchema),
    values: { name: '', email: invite.data?.email ?? '' },
    resetOptions: { keepDirtyValues: true },
  });
  const password = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: '' },
  });
  const code = useForm<z.infer<typeof codeSchema>>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: '' },
  });

  /** Run a step's request; the refusals every step shares are handled here. */
  const act = async (work: () => Promise<void>) => {
    setBusy(true);
    setNotice(null);
    try {
      await work();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) setStep({ kind: 'invalid' });
      else if (error instanceof ApiError && error.status === 409) {
        setStep({ kind: 'details' });
        details.setError('email', { message: t.errors.emailInUse });
      } else if (error instanceof ApiError && error.status === 400) {
        setNotice(t.errors.passkeyFailed);
      } else {
        setNotice(
          failureMessage(error, {
            cancelled: t.errors.passkeyCancelled,
            passkeyFailed: t.errors.passkeyFailed,
          }),
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const withPasskey = details.handleSubmit((values) =>
    act(async () => {
      const body = { token, name: values.name, email: values.email };
      const options = await api.request('POST', '/api/v1/auth/register/options', body);
      const credential = await createPasskey(options);
      const registered = await api.request('POST', '/api/v1/auth/register/verify', {
        ...body,
        credential,
      });
      setStep({ kind: 'codes', codes: registered.recovery_codes });
    }),
  );

  const toPassword = details.handleSubmit(() => {
    setNotice(null);
    setStep({ kind: 'password' });
  });

  const withPassword = password.handleSubmit((values) =>
    act(async () => {
      const { name, email } = details.getValues();
      try {
        const registered = await api.request('POST', '/api/v1/auth/register/password', {
          token,
          name: name.trim(),
          email: email.trim(),
          password: values.password,
        });
        // Only ever an authenticator link (never another scheme in an href).
        if (!registered.provisioning_uri.startsWith('otpauth://totp/')) {
          setNotice(copy.common.networkError);
          return;
        }
        setStep({ kind: 'totp', uri: registered.provisioning_uri });
      } catch (error) {
        const refused =
          error instanceof ApiError
            ? error.fieldErrors.find((field) => field.field.endsWith('password'))
            : undefined;
        if (refused === undefined) throw error;
        password.setError('password', {
          message:
            refused.code === 'password_too_short'
              ? t.errors.passwordShort
              : t.errors.passwordCommon,
        });
      }
    }),
  );

  const confirmCode = code.handleSubmit((values) =>
    act(async () => {
      try {
        const confirmed = await api.request('POST', '/api/v1/auth/totp/confirm', {
          code: values.code,
        });
        setStep({ kind: 'codes', codes: confirmed.recovery_codes });
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
        code.setError('code', { message: t.errors.codeWrong });
      }
    }),
  );

  const finish = () => {
    startSession(queryClient);
    // CR-030: her timezone follows the device's from the start (SET-1 "auto-detected").
    void adoptDeviceTimezone(queryClient);
    // J1 step 3: in a browser tab, the install guide comes next (ONB-1).
    navigate(needsInstallGuide() ? '/install' : '/today', { replace: true });
  };

  if (step.kind === 'codes') return <RecoveryCodesStep codes={step.codes} onDone={finish} />;

  if (step.kind === 'invalid' || (invite.data !== undefined && !invite.data.valid)) {
    return (
      <AuthPage focusKey={`${step.kind}:${String(dismissed)}`} title={t.title}>
        <ErrorState title={t.invalidTitle} body={t.invalidBody} />
      </AuthPage>
    );
  }

  if (step.kind === 'totp') {
    return (
      <AuthPage
        title={step.uri === null ? t.confirmTitle : t.totpTitle}
        {...(step.uri === null ? {} : { intro: t.totpBody })}
      >
        <Notice message={notice} onDismiss={dismiss} />
        {step.uri !== null && (
          <Card>
            <Stack gap={3}>
              <Button href={step.uri} variant="secondary">
                {t.openAuthenticator}
              </Button>
              <p>{t.secret}</p>
              <p translate="no">
                <strong>{secretOf(step.uri)}</strong>
              </p>
            </Stack>
          </Card>
        )}
        <form noValidate onSubmit={(event: FormEvent) => void confirmCode(event)}>
          <Stack gap={4}>
            <TextField
              label={t.code}
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              {...bindField(code, 'code')}
            />
            <Button type="submit" busy={busy}>
              {t.confirm}
            </Button>
          </Stack>
        </form>
      </AuthPage>
    );
  }

  if (invite.isPending) {
    return (
      <AuthPage focusKey={`${step.kind}:${String(dismissed)}`} title={t.title}>
        <Skeleton label={t.checking} shapes={['line', 'block', 'block']} />
      </AuthPage>
    );
  }

  if (invite.isError) {
    return (
      <AuthPage focusKey={`${step.kind}:${String(dismissed)}`} title={t.title}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void invite.refetch() }}
        />
      </AuthPage>
    );
  }

  if (step.kind === 'password') {
    return (
      <AuthPage focusKey={`${step.kind}:${String(dismissed)}`} title={t.passwordTitle}>
        <Notice message={notice} onDismiss={dismiss} />
        <form noValidate onSubmit={(event: FormEvent) => void withPassword(event)}>
          <Stack gap={4}>
            <TextField
              label={t.password}
              hint={t.passwordHint}
              type="password"
              autoComplete="new-password"
              {...bindField(password, 'password')}
            />
            <Button type="submit" busy={busy}>
              {t.continue}
            </Button>
            <Button variant="ghost" onClick={() => setStep({ kind: 'details' })}>
              {copy.common.back}
            </Button>
          </Stack>
        </form>
      </AuthPage>
    );
  }

  return (
    <AuthPage focusKey={`${step.kind}:${String(dismissed)}`} title={t.title} intro={t.intro}>
      <Notice message={notice} onDismiss={dismiss} />
      <form noValidate onSubmit={(event: FormEvent) => void withPasskey(event)}>
        <Stack gap={4}>
          <TextField
            label={t.name}
            hint={t.nameHint}
            autoComplete="name"
            {...bindField(details, 'name')}
          />
          <TextField
            label={t.email}
            type="email"
            autoComplete="email"
            {...bindField(details, 'email')}
          />
          <p>{t.passkeyHint}</p>
          <Button type="submit" icon="key" busy={busy}>
            {t.createPasskey}
          </Button>
          <Button variant="ghost" onClick={() => void toPassword()}>
            {t.usePassword}
          </Button>
        </Stack>
      </form>
    </AuthPage>
  );
}
