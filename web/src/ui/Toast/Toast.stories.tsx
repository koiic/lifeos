import type { Story } from '@ladle/react';

import { Stack } from '../Stack';
import { Toast } from './Toast';

export default { title: 'Toast' };

export const Tones: Story = () => (
  <Stack gap={3}>
    <Toast
      message="Check-in saved"
      tone="success"
      dismissLabel="Dismiss"
      onDismiss={() => undefined}
    />
    <Toast
      message="A new version is ready"
      action={{ label: 'Reload', onClick: () => undefined }}
      dismissLabel="Dismiss"
      onDismiss={() => undefined}
    />
    <Toast
      message="Couldn't save. We'll try again."
      tone="danger"
      dismissLabel="Dismiss"
      onDismiss={() => undefined}
    />
  </Stack>
);
