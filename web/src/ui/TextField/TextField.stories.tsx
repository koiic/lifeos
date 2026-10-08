import type { Story } from '@ladle/react';
import { useState } from 'react';

import { Stack } from '../Stack';
import { TextField } from './TextField';

export default { title: 'TextField' };

export const States: Story = () => {
  const [name, setName] = useState('Zee');
  return (
    <Stack gap={5}>
      <TextField label="Your name" name="name" value={name} onChange={setName} />
      <TextField
        label="Email"
        name="email"
        type="email"
        value=""
        hint="We only use it to sign you in"
        onChange={() => undefined}
      />
      <TextField
        label="Password"
        name="password"
        type="password"
        value=""
        error="Use at least 12 characters"
        onChange={() => undefined}
      />
    </Stack>
  );
};
