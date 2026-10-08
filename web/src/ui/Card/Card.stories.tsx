import type { Story } from '@ladle/react';

import { Button } from '../Button';
import { Chip } from '../Chip';
import { Stack } from '../Stack';
import { Card } from './Card';

export default { title: 'Card' };

export const Tones: Story = () => (
  <Stack gap={3}>
    <Card>
      <h2>Surface</h2>
      <p>Cards, sheets</p>
    </Card>
    <Card tone="accent">
      <h2>Day 23</h2>
      <p>Period in about 5 days</p>
    </Card>
    <Card tone="fertile">Estimated fertile window</Card>
    <Card tone="sun">Streak: 7 days</Card>
    <Card tone="lilac">Dentist, 14:30</Card>
    <Card tone="butter">Vitamin D, 1 tablet</Card>
  </Stack>
);

export const Sticker: Story = () => (
  <Card tone="sun" sticker>
    <h2>Nice, 7 days in a row</h2>
  </Card>
);

/** Controls on every tone: the focus ring must follow the card's text colour (CR-024). */
export const WithControls: Story = () => {
  const tones = ['surface', 'accent', 'fertile', 'sun', 'lilac', 'butter'] as const;
  return (
    <Stack gap={3}>
      {tones.map((tone) => (
        <Card key={tone} tone={tone}>
          <Stack direction="row" gap={2} wrap>
            <Button>Save</Button>
            <Button variant="ghost">Later</Button>
            <Chip pressed={tone === 'accent'} onChange={() => undefined}>
              Cramps
            </Chip>
          </Stack>
        </Card>
      ))}
    </Stack>
  );
};
