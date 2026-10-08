import type { Story } from '@ladle/react';
import { useState } from 'react';

import { Stack } from '../Stack';
import { Switch } from './Switch';

export default { title: 'Switch' };

export const States: Story = () => {
  const [discreet, setDiscreet] = useState(true);
  const [lock, setLock] = useState(false);
  return (
    <Stack gap={5}>
      <Switch label="Discreet notifications" checked={discreet} onChange={setDiscreet} />
      <Switch
        label="App lock"
        description="Asks after 5 minutes away"
        checked={lock}
        onChange={setLock}
      />
    </Stack>
  );
};
