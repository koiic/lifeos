import type { Story } from '@ladle/react';

import { Skeleton } from './Skeleton';

export default { title: 'Skeleton' };

export const Today: Story = () => (
  <Skeleton label="Loading today" shapes={['line', 'line', 'block', 'circle']} />
);
