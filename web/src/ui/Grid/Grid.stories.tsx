import type { Story } from '@ladle/react';

import { Card } from '../Card';
import { Grid } from './Grid';

export default { title: 'Layout / Grid' };

export const TwoColumns: Story = () => (
  <Grid columns={2} gap={3}>
    <Card tone="fertile">Mood</Card>
    <Card tone="lilac">Energy</Card>
    <Card tone="sun">Sleep</Card>
    <Card tone="butter">Flow</Card>
  </Grid>
);
