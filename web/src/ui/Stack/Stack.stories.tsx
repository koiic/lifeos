import type { Story } from '@ladle/react';

import { Card } from '../Card';
import { Stack } from './Stack';

export default { title: 'Layout / Stack' };

export const Column: Story = () => (
  <Stack gap={3}>
    <Card>One</Card>
    <Card>Two</Card>
    <Card>Three</Card>
  </Stack>
);

export const Row: Story = () => (
  <Stack direction="row" gap={2} align="center" justify="between">
    <Card>Left</Card>
    <Card>Right</Card>
  </Stack>
);
