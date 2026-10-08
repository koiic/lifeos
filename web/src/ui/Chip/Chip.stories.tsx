import type { Story } from '@ladle/react';
import { useState } from 'react';

import { Stack } from '../Stack';
import { Chip, ChipGroup } from './Chip';

export default { title: 'Chip' };

export const Toggle: Story = () => {
  const [cramps, setCramps] = useState(true);
  const [headache, setHeadache] = useState(false);
  return (
    <Stack direction="row" gap={2} wrap>
      <Chip pressed={cramps} onChange={setCramps}>
        Cramps
      </Chip>
      <Chip pressed={headache} onChange={setHeadache}>
        Headache
      </Chip>
    </Stack>
  );
};

export const Choice: Story = () => {
  const [flow, setFlow] = useState<'light' | 'medium' | 'heavy'>('medium');
  return (
    <ChipGroup
      legend="Flow"
      name="flow"
      options={[
        { value: 'light', label: 'Light' },
        { value: 'medium', label: 'Medium' },
        { value: 'heavy', label: 'Heavy' },
      ]}
      value={flow}
      onChange={setFlow}
    />
  );
};
