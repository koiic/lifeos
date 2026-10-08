import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type FormEvent, type ReactNode, useId, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { copy } from '../../copy/en-GB';
import { api } from '../../lib/api';
import { useRecentAuth } from '../../lib/auth/recentAuth';
import { hasReason, REASON, signOut } from '../../lib/auth/session';
import { createPasskey, PasskeyCancelled } from '../../lib/auth/webauthn';
import { formatDateTime } from '../../lib/dates';
import { bindField } from '../../lib/forms/bindField';
import { zodResolver } from '../../lib/forms/zodResolver';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { CodeList } from '../../ui/CodeList';
import { Dialog } from '../../ui/Dialog';
import { EmptyState } from '../../ui/EmptyState';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import { TextField } from '../../ui/TextField';
import { Toast } from '../../ui/Toast';

const t = copy.settings.security;

const pinSchema = z
  .object({
    pin: z.string().regex(/^\d{6}$/, t.pin.errors.digits),
    repeat: z.string(),
  })
  .refine((values) => values.pin === values.repeat, {
    message: t.pin.errors.match,
    path: ['repeat'],
  });

type SectionKey = 'passkeys' | 'sessions' | 'pin' | 'codes';

/** The outcome of the last change, shown in the section where it happened. */
interface Notice {
  section: SectionKey;
  message: string;
  tone: 'success' | 'danger';
}

/** A change she asked for: which button started it, where to report, what it does. */
interface Change {
  key: string;
  section: SectionKey;
  action: () => Promise<string>;
  failure?: (error: unknown) => string | undefined;
}

type Confirming = { kind: 'passkey'; id: string; name: string } | { kind: 'pin' } | null;

/** One settings card: a labelled region with a heading, and its own feedback. */
function Section({
  title,
  intro,
  notice,
  onDismiss,
  children,
}: {
  title: string;
  intro: string;
  notice: Notice | null;
  onDismiss: () => void;
  children: ReactNode;
}) {
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  return (
    <Card as="section" labelledBy={id}>
      <h2 id={id} ref={heading} tabIndex={-1}>
        {title}
      </h2>
      <p>{intro}</p>
      {notice !== null && (
        <Toast
          tone={notice.tone}
          message={notice.message}
          dismissLabel={copy.common.dismiss}
          onDismiss={() => {
            onDismiss();
            // The message is gone: keep keyboard users in this section (WCAG 2.4.3).
            heading.current?.focus();
          }}
        />
      )}
      {children}
    </Card>
  );
}

/** Loading and error states for a list in a card (spec 5.2: every network action). */
function ListState({ status, onRetry }: { status: 'pending' | 'error'; onRetry: () => void }) {
  if (status === 'pending') {
    return <Skeleton label={copy.common.loading} shapes={['line', 'line']} />;
  }
  return (
    <ErrorState
      title={copy.errors.title}
      body={copy.common.networkError}
      retry={{ label: copy.common.retry, onClick: onRetry }}
    />
  );
}

/**
 * Spec 5.2 Settings → "security and sessions": passkeys (Ibrahim, 2026-10-08), signed-in devices
 * (AUTH-5), the app-lock PIN (AUTH-6), recovery codes (AUTH-4) and signing out. Changes that need
 * recent authentication ask "Confirm it's you" first (9.2); removals ask before they happen.
 */
export function SecurityScreen() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [notice, setNotice] = useState<Notice | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [confirming, setConfirming] = useState<Confirming>(null);
  // Every action in flight, so each button keeps its own busy state.
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());

  const sessions = useQuery({
    queryKey: ['sessions'],
    queryFn: () => api.request('GET', '/api/v1/auth/sessions'),
  });
  const passkeys = useQuery({
    queryKey: ['passkeys'],
    queryFn: () => api.request('GET', '/api/v1/auth/passkeys'),
  });
  // Unknown until the list loads: then "Confirm it's you" offers both ways.
  const recentAuth = useRecentAuth(passkeys.isSuccess ? passkeys.data.items.length > 0 : undefined);

  const pinForm = useForm<z.infer<typeof pinSchema>>({
    resolver: zodResolver(pinSchema),
    defaultValues: { pin: '', repeat: '' },
  });

  const change = useMutation({
    mutationFn: ({ action }: Change) => recentAuth.run(action),
    onMutate: ({ key }) => {
      setNotice(null);
      setPending((keys) => new Set(keys).add(key));
    },
    onSettled: (_data, _error, { key }) =>
      setPending((keys) => {
        const next = new Set(keys);
        next.delete(key);
        return next;
      }),
    onSuccess: (message, { section }) => {
      if (message !== undefined) setNotice({ section, message, tone: 'success' });
    },
    onError: (error, { section, failure }) => {
      const message =
        failure?.(error) ?? (error instanceof TypeError ? copy.common.networkError : t.failed);
      setNotice({ section, message, tone: 'danger' });
    },
  });
  const busy = (key: string) => pending.has(key);
  const noticeFor = (section: SectionKey) => (notice?.section === section ? notice : null);

  const addPasskey = () =>
    change.mutate({
      key: 'passkey:add',
      section: 'passkeys',
      action: async () => {
        const options = await api.request('POST', '/api/v1/auth/passkeys/options', {});
        const credential = await createPasskey(options);
        await api.request('POST', '/api/v1/auth/passkeys/verify', { credential });
        await queryClient.invalidateQueries({ queryKey: ['passkeys'] });
        return t.passkeys.addedDone;
      },
      failure: (error) => (error instanceof PasskeyCancelled ? t.passkeys.cancelled : undefined),
    });

  const removePasskey = (id: string) =>
    change.mutate({
      key: `passkey:remove:${id}`,
      section: 'passkeys',
      action: async () => {
        await api.request('DELETE', '/api/v1/auth/passkeys/{passkey_id}', undefined, {
          passkey_id: id,
        });
        await queryClient.invalidateQueries({ queryKey: ['passkeys'] });
        return t.passkeys.removed;
      },
      failure: (error) =>
        hasReason(error, 409, REASON.lastSignInMethod) ? t.passkeys.lastOne : undefined,
    });

  const revoke = (id: string) =>
    change.mutate({
      key: `session:${id}`,
      section: 'sessions',
      action: async () => {
        await api.request('DELETE', '/api/v1/auth/sessions/{session_id}', undefined, {
          session_id: id,
        });
        await queryClient.invalidateQueries({ queryKey: ['sessions'] });
        return t.sessions.revoked;
      },
    });

  const savePin = pinForm.handleSubmit((values) =>
    change.mutate({
      key: 'pin:save',
      section: 'pin',
      action: async () => {
        await api.request('PUT', '/api/v1/auth/app-lock', { pin: values.pin });
        pinForm.reset();
        return t.pin.saved;
      },
    }),
  );

  const removePin = () =>
    change.mutate({
      key: 'pin:remove',
      section: 'pin',
      action: async () => {
        await api.request('PUT', '/api/v1/auth/app-lock', { pin: null });
        return t.pin.removed;
      },
    });

  const regenerate = () =>
    change.mutate({
      key: 'codes',
      section: 'codes',
      action: async () => {
        const result = await api.request('POST', '/api/v1/auth/recovery-codes');
        setCodes(result.recovery_codes);
        return t.codes.oldStopWorking;
      },
    });

  const confirmRemoval = () => {
    if (confirming?.kind === 'passkey') removePasskey(confirming.id);
    if (confirming?.kind === 'pin') removePin();
    setConfirming(null);
  };

  const leave = async () => {
    await signOut(queryClient);
    navigate('/signin', { replace: true });
  };

  const dismiss = () => setNotice(null);
  const removal =
    confirming?.kind === 'passkey'
      ? {
          title: t.passkeys.confirmTitle,
          body: t.passkeys.confirmBody(confirming.name),
          action: t.passkeys.confirmRemove,
        }
      : { title: t.pin.confirmTitle, body: t.pin.confirmBody, action: t.pin.confirmRemove };

  return (
    <Stack as="main" inset="page" gap={5}>
      <h1>{t.title}</h1>

      <Section
        title={t.passkeys.title}
        intro={t.passkeys.intro}
        notice={noticeFor('passkeys')}
        onDismiss={dismiss}
      >
        {passkeys.isSuccess ? (
          passkeys.data.items.length === 0 ? (
            <EmptyState title={t.passkeys.empty} icon="key" />
          ) : (
            <Stack as="ul" gap={3}>
              {passkeys.data.items.map((passkey) => (
                <li key={passkey.id}>
                  <Stack direction="row" gap={3} justify="between" align="center">
                    <Stack gap={1}>
                      <strong>{passkey.nickname}</strong>
                      <span>{t.passkeys.added(formatDateTime(passkey.created_at))}</span>
                      <span>
                        {passkey.last_used_at === null
                          ? t.passkeys.neverUsed
                          : t.passkeys.lastUsed(formatDateTime(passkey.last_used_at))}
                      </span>
                      {passkey.backed_up && <span>{t.passkeys.synced}</span>}
                    </Stack>
                    <Button
                      variant="icon"
                      icon="trash"
                      label={t.passkeys.remove(passkey.nickname)}
                      busy={busy(`passkey:remove:${passkey.id}`)}
                      onClick={() =>
                        setConfirming({ kind: 'passkey', id: passkey.id, name: passkey.nickname })
                      }
                    />
                  </Stack>
                </li>
              ))}
            </Stack>
          )
        ) : (
          <ListState status={passkeys.status} onRetry={() => void passkeys.refetch()} />
        )}
        <Button variant="secondary" icon="key" busy={busy('passkey:add')} onClick={addPasskey}>
          {t.passkeys.add}
        </Button>
      </Section>

      <Section
        title={t.sessions.title}
        intro={t.sessions.intro}
        notice={noticeFor('sessions')}
        onDismiss={dismiss}
      >
        {sessions.isSuccess ? (
          <Stack as="ul" gap={3}>
            {sessions.data.items.map((session) => {
              const device = session.device_label ?? t.sessions.unknownDevice;
              return (
                <li key={session.id}>
                  <Stack gap={2}>
                    <Stack gap={1}>
                      <strong>{device}</strong>
                      <span>{t.sessions.lastActive(formatDateTime(session.last_seen_at))}</span>
                      {session.current && <span>{t.sessions.thisDevice}</span>}
                    </Stack>
                    {!session.current && (
                      <Button
                        variant="secondary"
                        busy={busy(`session:${session.id}`)}
                        onClick={() => revoke(session.id)}
                      >
                        {t.sessions.revoke(device)}
                      </Button>
                    )}
                  </Stack>
                </li>
              );
            })}
          </Stack>
        ) : (
          <ListState status={sessions.status} onRetry={() => void sessions.refetch()} />
        )}
      </Section>

      <Section
        title={t.pin.title}
        intro={t.pin.intro}
        notice={noticeFor('pin')}
        onDismiss={dismiss}
      >
        <form noValidate onSubmit={(event: FormEvent) => void savePin(event)}>
          <Stack gap={3}>
            <TextField
              label={t.pin.new}
              type="password"
              inputMode="numeric"
              maxLength={6}
              autoComplete="off"
              {...bindField(pinForm, 'pin')}
            />
            <TextField
              label={t.pin.repeat}
              type="password"
              inputMode="numeric"
              maxLength={6}
              autoComplete="off"
              {...bindField(pinForm, 'repeat')}
            />
            <Button type="submit" busy={busy('pin:save')}>
              {t.pin.save}
            </Button>
            <Button
              variant="ghost"
              busy={busy('pin:remove')}
              onClick={() => setConfirming({ kind: 'pin' })}
            >
              {t.pin.remove}
            </Button>
          </Stack>
        </form>
      </Section>

      <Section
        title={t.codes.title}
        intro={t.codes.intro}
        notice={noticeFor('codes')}
        onDismiss={dismiss}
      >
        {codes !== null ? (
          <Stack gap={3}>
            <CodeList
              label={copy.auth.codes.list}
              codes={codes}
              copyLabel={copy.auth.codes.copy}
              copiedLabel={copy.auth.codes.copied}
              copyFailedLabel={copy.auth.codes.copyFailed}
            />
            <Button onClick={() => setCodes(null)}>{copy.auth.codes.done}</Button>
          </Stack>
        ) : (
          <Button variant="secondary" busy={busy('codes')} onClick={regenerate}>
            {t.codes.regenerate}
          </Button>
        )}
      </Section>

      <Button variant="secondary" onClick={() => void leave()}>
        {t.signOut}
      </Button>

      <Dialog
        open={confirming !== null}
        alert
        title={removal.title}
        description={removal.body}
        onClose={() => setConfirming(null)}
        actions={
          <Stack direction="row" gap={3} justify="end" wrap>
            <Button variant="secondary" onClick={() => setConfirming(null)}>
              {copy.common.cancel}
            </Button>
            <Button variant="danger" onClick={confirmRemoval}>
              {removal.action}
            </Button>
          </Stack>
        }
      />
      {recentAuth.dialog}
    </Stack>
  );
}
