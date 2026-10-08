import type { Story } from '@ladle/react';

import { copy } from '../../copy/en-GB';
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
      message={copy.update.ready}
      action={{ label: copy.update.refresh, onClick: () => undefined }}
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

/** App-wide (spec 11.3's update prompt): fixed at the bottom, above the page. */
export const Floating: Story = () => (
  <Toast
    placement="floating"
    message={copy.update.ready}
    action={{ label: copy.update.refresh, onClick: () => undefined }}
    dismissLabel={copy.common.dismiss}
    onDismiss={() => undefined}
  />
);
