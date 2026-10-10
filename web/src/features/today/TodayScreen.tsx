import { useEffect, useId, useRef, useState } from 'react';

import { copy } from '../../copy/en-GB';
import { cityOf, formatTodayDate, nowIso } from '../../lib/dates';
import { greetingFor } from '../../lib/greeting';
import { type Me, useChangeProfile, useMe } from '../../lib/me/me';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';

const t = copy.today;
// The device timezone she chose to keep her own over, on this device (CR-030).
const KEPT_KEY = 'lifeos.timezone-kept';

function kept(): string | null {
  try {
    return localStorage.getItem(KEPT_KEY);
  } catch {
    return null;
  }
}

function keep(zone: string): void {
  try {
    localStorage.setItem(KEPT_KEY, zone);
  } catch {
    // Storage blocked: the prompt may come back next time; nothing else is affected.
  }
}

/** Spec 11.7, CR-030: "You seem to be in Lagos — switch timezone?" */
function TimezonePrompt({ me, onSwitched }: { me: Me; onSwitched: (city: string) => void }) {
  const id = useId();
  const change = useChangeProfile();
  const [hidden, setHidden] = useState(false);
  const zone = me.device_timezone;
  if (hidden || !me.timezone_differs || zone === null || kept() === zone) return null;
  const city = cityOf(zone);
  return (
    <Card as="section" labelledBy={id}>
      <h2 id={id}>{t.timezone.title(city)}</h2>
      <p>{t.timezone.body}</p>
      {change.isError && <p role="alert">{copy.common.networkError}</p>}
      <Button
        busy={change.isPending}
        onClick={() => change.mutate({ timezone: zone }, { onSuccess: () => onSwitched(city) })}
      >
        {t.timezone.switch(city)}
      </Button>
      <Button
        variant="ghost"
        onClick={() => {
          keep(zone);
          setHidden(true);
        }}
      >
        {t.timezone.keep}
      </Button>
    </Card>
  );
}

/**
 * Spec 5.2 Today (`/today`): the greeting and date (TOD-1) in her profile timezone (11.7). The
 * cycle card, check-in, list and streak (TOD-2–7) arrive with their tasks.
 */
export function TodayScreen() {
  const me = useMe();
  const heading = useRef<HTMLHeadingElement>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (me.isSuccess) heading.current?.focus();
  }, [me.isSuccess]);

  if (me.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'block']} />
      </Stack>
    );
  }
  if (me.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void me.refetch() }}
        />
      </Stack>
    );
  }

  const { profile } = me.data;
  const now = nowIso();
  const greeting = t.greeting[greetingFor(now, profile.timezone)];
  return (
    <Stack as="main" inset="page" gap={5}>
      <Stack gap={1}>
        <p>{formatTodayDate(now, profile.timezone)}</p>
        <h1 ref={heading} tabIndex={-1}>
          {t.greetingWithName(greeting, profile.display_name)}
        </h1>
      </Stack>
      <p role="status">{status}</p>
      <TimezonePrompt me={me.data} onSwitched={(city) => setStatus(t.timezone.switched(city))} />
    </Stack>
  );
}
