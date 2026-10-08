// "Recent auth" (spec 9.2, 12.3, CR-017): sensitive actions need a passkey or password check
// within 5 minutes. `useRecentAuth().run(action)` tries the action; if the server asks for recent
// authentication, it shows "Confirm it's you" and, once she has, tries the action again.
import { type FormEvent, type ReactElement, useCallback, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { copy } from '../../copy/en-GB';
import { Button } from '../../ui/Button';
import { Dialog } from '../../ui/Dialog';
import { Stack } from '../../ui/Stack';
import { TextField } from '../../ui/TextField';
import { Toast } from '../../ui/Toast';
import { api } from '../api';
import { bindField } from '../forms/bindField';
import { zodResolver } from '../forms/zodResolver';
import { hasReason, REASON } from './session';
import { PasskeyCancelled, signWithPasskey } from './webauthn';

const t = copy.auth.confirm;

const passwordSchema = z.object({
  password: z.string().min(1, t.errors.password),
  totp: z.string().regex(/^\d{6}$/, t.errors.code),
});
type PasswordValues = z.infer<typeof passwordSchema>;

interface DialogProps {
  open: boolean;
  /** She has a passkey: confirm with it; none: password and code; unknown (`undefined`, e.g.
   * the list failed to load): both are offered. */
  hasPasskeys: boolean | undefined;
  onDone: () => void;
  onCancel: () => void;
}

function RecentAuthDialog({ open, hasPasskeys, onDone, onCancel }: DialogProps) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: '', totp: '' },
  });

  const attempt = async (verify: () => Promise<void>) => {
    setBusy(true);
    setFailure(null);
    try {
      await verify();
      form.reset();
      onDone();
    } catch (error) {
      if (error instanceof TypeError) setFailure(copy.common.networkError);
      else if (!(error instanceof PasskeyCancelled)) setFailure(t.failed);
    } finally {
      setBusy(false);
    }
  };

  // A cancelled password is forgotten at once, not kept until the dialog next opens.
  const cancel = () => {
    form.reset();
    onCancel();
  };

  const withPasskey = () =>
    attempt(async () => {
      const options = await api.request('POST', '/api/v1/auth/reauth/options', {
        purpose: 'reauth',
      });
      const credential = await signWithPasskey(options);
      await api.request('POST', '/api/v1/auth/reauth/verify', { credential });
    });

  const withPassword = form.handleSubmit((values) =>
    attempt(async () => {
      await api.request('POST', '/api/v1/auth/reauth/verify', values);
    }),
  );

  return (
    <Dialog
      open={open}
      title={t.title}
      description={t.body}
      onClose={cancel}
      actions={
        <Stack gap={3}>
          {failure !== null && (
            <Toast
              tone="danger"
              message={failure}
              dismissLabel={copy.common.dismiss}
              onDismiss={() => setFailure(null)}
            />
          )}
          {hasPasskeys !== false && (
            <Button icon="key" busy={busy} onClick={() => void withPasskey()}>
              {t.passkey}
            </Button>
          )}
          {hasPasskeys !== true && (
            <form noValidate onSubmit={(event: FormEvent) => void withPassword(event)}>
              <Stack gap={3}>
                <TextField
                  label={t.password}
                  type="password"
                  autoComplete="current-password"
                  {...bindField(form, 'password')}
                />
                <TextField
                  label={t.code}
                  inputMode="numeric"
                  maxLength={6}
                  autoComplete="one-time-code"
                  {...bindField(form, 'totp')}
                />
                <Button type="submit" busy={busy}>
                  {t.submit}
                </Button>
              </Stack>
            </form>
          )}
          <Button variant="ghost" onClick={cancel}>
            {copy.common.cancel}
          </Button>
        </Stack>
      }
    />
  );
}

export interface RecentAuth {
  /** Run `action`; if it needs recent auth, confirm and run it once more. `undefined` if she
   * cancelled. Other errors are thrown as usual. */
  run: <T>(action: () => Promise<T>) => Promise<T | undefined>;
  dialog: ReactElement;
}

export function useRecentAuth(hasPasskeys: boolean | undefined): RecentAuth {
  const [open, setOpen] = useState(false);
  // Each opening is a new dialog: a password typed and then abandoned is not kept.
  const [round, setRound] = useState(0);
  const pending = useRef<((confirmed: boolean) => void) | null>(null);

  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    try {
      return await action();
    } catch (error) {
      if (!hasReason(error, 403, REASON.reauthRequired)) throw error;
      const confirmed = await new Promise<boolean>((resolve) => {
        pending.current = resolve;
        setRound((n) => n + 1);
        setOpen(true);
      });
      return confirmed ? await action() : undefined;
    }
  }, []);

  const finish = (confirmed: boolean) => {
    setOpen(false);
    pending.current?.(confirmed);
    pending.current = null;
  };

  return {
    run,
    dialog: (
      <RecentAuthDialog
        key={round}
        open={open}
        hasPasskeys={hasPasskeys}
        onDone={() => finish(true)}
        onCancel={() => finish(false)}
      />
    ),
  };
}
