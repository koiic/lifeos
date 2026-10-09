import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import {
  deniedSteps,
  enableNotifications,
  type PushState,
  pushState,
  sendTestPush,
} from '../../lib/push/push';
import { Button } from '../../ui/Button';
import { NotificationPermissionCard } from '../../ui/NotificationPermissionCard';
import { Stack } from '../../ui/Stack';

const t = copy.notifications;

/**
 * Spec 5.2 "Notifications opt-in" (`/setup/notifications`), ONB-3, J1 step 5: permission is
 * asked only when she taps (iOS refuses otherwise, 10.6); once on, a test notification goes at
 * once; if her phone blocks them, how to allow them again; on iPhone in a tab, install first.
 */
export function NotificationsScreen() {
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  const [state, setState] = useState<PushState>(() => pushState());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | undefined>(undefined);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  const test = async () => {
    try {
      setStatus((await sendTestPush()) > 0 ? t.testSent : t.testFailed);
    } catch (error) {
      setStatus(error instanceof TypeError ? copy.common.networkError : t.testFailed);
    }
  };

  // Runs in the button's click handler: the permission request needs her tap.
  const enable = async () => {
    setBusy(true);
    setStatus(undefined);
    try {
      const result = await enableNotifications();
      setState(result);
      if (result === 'granted') await test();
    } catch (error) {
      setStatus(error instanceof TypeError ? copy.common.networkError : t.failed);
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async () => {
    setBusy(true);
    setStatus(undefined);
    await test();
    setBusy(false);
  };

  const card = (() => {
    switch (state) {
      case 'prompt':
        return {
          ...t.prompt,
          action: { label: t.enable, onClick: () => void enable(), busy },
        };
      case 'granted':
        return {
          ...t.granted,
          action: { label: t.sendTest, onClick: () => void sendTest(), busy },
        };
      case 'denied':
        return {
          ...t.denied,
          steps: { label: t.denied.stepsLabel, items: t.denied.steps[deniedSteps()] },
        };
      case 'needs-install':
        return { ...t.needsInstall, action: { label: t.needsInstall.action, href: '/install' } };
      case 'unsupported':
        return t.unsupported;
    }
  })();

  return (
    <Stack as="main" inset="page" gap={5}>
      <Stack gap={2}>
        <h1 ref={heading} tabIndex={-1}>
          {t.title}
        </h1>
        <p>{t.intro}</p>
      </Stack>
      <NotificationPermissionCard
        state={state}
        title={card.title}
        body={card.body}
        {...('action' in card ? { action: card.action } : {})}
        {...('steps' in card ? { steps: card.steps } : {})}
        {...(status === undefined ? {} : { status })}
      />
      <Button variant="ghost" onClick={() => navigate('/today', { replace: true })}>
        {t.continue}
      </Button>
    </Stack>
  );
}
