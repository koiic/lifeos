import type { Story } from '@ladle/react';

import { LockScreen } from './LockScreen';

export default { title: 'LockScreen' };

const noop = () => undefined;

export const Locked: Story = () => (
  <LockScreen
    title="Life OS is locked"
    passkey={{ label: 'Unlock with passkey', onUnlock: noop }}
    pin={{
      label: 'PIN',
      submitLabel: 'Unlock',
      onSubmit: noop,
      invalidMessage: 'Enter your 6-digit PIN',
    }}
    signOut={{ label: 'Sign out', onClick: noop }}
  />
);

export const WrongPin: Story = () => (
  <LockScreen
    title="Life OS is locked"
    pin={{
      label: 'PIN',
      submitLabel: 'Unlock',
      onSubmit: noop,
      invalidMessage: 'Enter your 6-digit PIN',
      error: 'Wrong PIN. Try again.',
    }}
    signOut={{ label: 'Sign out', onClick: noop }}
  />
);

/** Shown while the app is in the background, so the app switcher shows no content. */
export const Cover: Story = () => <LockScreen title="Life OS is locked" />;

/** Unlocking: both ways show they are working and cannot be pressed twice. */
export const Busy: Story = () => (
  <LockScreen
    title="Life OS is locked"
    passkey={{ label: 'Unlock with passkey', onUnlock: noop, busy: true }}
    pin={{
      label: 'PIN',
      submitLabel: 'Unlock',
      onSubmit: noop,
      invalidMessage: 'Enter your 6-digit PIN',
      busy: true,
    }}
    signOut={{ label: 'Sign out', onClick: noop }}
  />
);
