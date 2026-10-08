import { type ReactNode, useEffect, useRef } from 'react';

import { copy } from '../../copy/en-GB';
import { ApiError } from '../../lib/api';
import { PasskeyCancelled } from '../../lib/auth/webauthn';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { CodeList } from '../../ui/CodeList';
import { Stack } from '../../ui/Stack';
import { Toast } from '../../ui/Toast';

/**
 * The frame of the signed-out screens: a page with a heading and an optional intro. Focus moves
 * to the heading when the page appears and whenever `focusKey` changes (a new step or mode, a
 * dismissed message), so keyboard and screen reader users keep their place (WCAG 2.4.3).
 */
export function AuthPage({
  title,
  intro,
  focusKey,
  children,
}: {
  title: string;
  intro?: string;
  focusKey?: string;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [focusKey]);
  return (
    <Stack as="main" inset="page" gap={5}>
      <Stack gap={2}>
        <h1 ref={heading} tabIndex={-1}>
          {title}
        </h1>
        {intro !== undefined && <p>{intro}</p>}
      </Stack>
      {children}
    </Stack>
  );
}

/** A message about the last action; errors are announced (alert), others politely. */
export function Notice({
  message,
  tone = 'danger',
  onDismiss,
}: {
  message: string | null;
  tone?: 'danger' | 'success';
  onDismiss: () => void;
}) {
  if (message === null) return null;
  return (
    <Toast tone={tone} message={message} dismissLabel={copy.common.dismiss} onDismiss={onDismiss} />
  );
}

/** AUTH-4: the codes, shown once, with the step to move on. */
export function RecoveryCodesStep({
  codes,
  onDone,
}: {
  codes: readonly string[];
  onDone: () => void;
}) {
  const t = copy.auth.codes;
  return (
    <AuthPage title={t.title} intro={t.body}>
      <Card>
        <CodeList
          label={t.list}
          codes={codes}
          copyLabel={t.copy}
          copiedLabel={t.copied}
          copyFailedLabel={t.copyFailed}
        />
      </Card>
      <Button onClick={onDone}>{t.done}</Button>
    </AuthPage>
  );
}

/** Minutes to wait after an AUTH-7 lockout (rounded up; at least one). */
export function lockedMinutes(error: ApiError): number {
  return Math.max(1, Math.ceil((error.retryAfterS ?? 900) / 60));
}

/**
 * The message for a failure that is not specific to one screen: a dismissed passkey prompt, an
 * AUTH-7 lockout, a refused sign-in, no connection (fetch's TypeError), or the browser failing to
 * make or use a passkey.
 */
export function failureMessage(
  error: unknown,
  messages: { cancelled: string; passkeyFailed: string },
): string {
  if (error instanceof PasskeyCancelled) return messages.cancelled;
  if (error instanceof ApiError) {
    if (error.status === 429) return copy.auth.signIn.locked(lockedMinutes(error));
    if (error.status === 401) return copy.auth.signIn.failed;
    return copy.common.networkError;
  }
  if (error instanceof TypeError) return copy.common.networkError;
  return messages.passkeyFailed;
}
