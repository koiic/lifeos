import type { Story } from '@ladle/react';

import { EmptyState } from './EmptyState';

export default { title: 'EmptyState' };

export const WithAction: Story = () => (
  <EmptyState
    icon="calendar"
    title="Nothing planned"
    body="Add an appointment and it shows here."
    action={{ label: 'Add appointment', onClick: () => undefined }}
  />
);

export const NoAction: Story = () => (
  <EmptyState title="All caught up" body="Nothing else for today." />
);
