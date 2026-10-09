import type { Story } from '@ladle/react';

import { copy } from '../../copy/en-GB';
import { NotificationPermissionCard } from './NotificationPermissionCard';

export default { title: 'NotificationPermissionCard' };

const t = copy.notifications;
const noop = () => undefined;

export const Prompt: Story = () => (
  <NotificationPermissionCard
    state="prompt"
    title={t.prompt.title}
    body={t.prompt.body}
    action={{ label: t.enable, onClick: noop }}
  />
);

export const Granted: Story = () => (
  <NotificationPermissionCard
    state="granted"
    title={t.granted.title}
    body={t.granted.body}
    action={{ label: t.sendTest, onClick: noop }}
    status={t.testSent}
  />
);

export const Denied: Story = () => (
  <NotificationPermissionCard
    state="denied"
    title={t.denied.title}
    body={t.denied.body}
    steps={{ label: t.denied.stepsLabel, items: t.denied.steps.ios }}
  />
);

export const NeedsInstall: Story = () => (
  <NotificationPermissionCard
    state="needs-install"
    title={t.needsInstall.title}
    body={t.needsInstall.body}
    action={{ label: t.needsInstall.action, href: '/install' }}
  />
);

export const Unsupported: Story = () => (
  <NotificationPermissionCard
    state="unsupported"
    title={t.unsupported.title}
    body={t.unsupported.body}
  />
);
