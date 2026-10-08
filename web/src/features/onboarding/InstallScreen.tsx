import { useEffect, useRef } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import {
  currentPlatform,
  dismissInstall,
  isStandalone,
  type Platform,
} from '../../lib/install/install';
import { InstallGuide, type InstallStep } from '../../ui/InstallGuide';
import { Stack } from '../../ui/Stack';

const t = copy.install;

/** The illustration for each step, per platform (the step text is in the copy). */
const ICONS: Record<Platform, readonly InstallStep['icon'][]> = {
  ios: ['share', 'addToHome', 'home'],
  iosOtherBrowser: ['info', 'share', 'home'],
  android: ['menu', 'addToHome', 'home'],
  other: ['menu', 'addToHome', 'home'],
};

/**
 * Spec 5.2 "Install guide" (`/install`), ONB-1, J1 step 3: in a browser tab, the steps for this
 * platform; already installed, straight on to Today. "Not now" is remembered (dismissible).
 */
export function InstallScreen() {
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  // She arrives from a button that is now gone: keep her place (WCAG 2.4.3).
  useEffect(() => {
    heading.current?.focus();
  }, []);
  if (isStandalone()) return <Navigate to="/today" replace />;

  const platform = currentPlatform();
  const steps = t.steps[platform].map((text, index) => ({
    icon: ICONS[platform][index] ?? 'home',
    text,
  }));

  return (
    <Stack as="main" inset="page" gap={5}>
      <Stack gap={2}>
        <h1 ref={heading} tabIndex={-1}>
          {t.title}
        </h1>
        <p>{t.intro}</p>
      </Stack>
      <InstallGuide
        label={t.stepsLabel}
        steps={steps}
        note={t.note}
        continueLabel={t.continue}
        onContinue={() => {
          dismissInstall();
          navigate('/today', { replace: true });
        }}
      />
    </Stack>
  );
}
