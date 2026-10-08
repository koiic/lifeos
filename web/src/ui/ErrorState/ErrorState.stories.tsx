import type { Story } from '@ladle/react';

import { ErrorState } from './ErrorState';

export default { title: 'ErrorState' };

export const WithRetry: Story = () => (
  <ErrorState
    title="Couldn't load this"
    body="Check your connection and try again."
    retry={{ label: 'Try again', onClick: () => undefined }}
  />
);

export const WithoutRetry: Story = () => (
  <ErrorState
    title="Couldn't save this"
    body="Your entry is kept on this phone and will sync later."
  />
);
