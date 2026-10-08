import type { Story } from '@ladle/react';
import { useState } from 'react';

import { Stack } from '../Stack';
import { TextField } from '../TextField';
import { Button } from './Button';

export default { title: 'Button' };

export const Variants: Story = () => (
  <Stack gap={3} align="start">
    <Button>Save check-in</Button>
    <Button variant="secondary">Edit</Button>
    <Button variant="ghost">Not now</Button>
    <Button variant="danger">Delete account</Button>
    <Button icon="plus">Add appointment</Button>
    <Button variant="icon" icon="close" label="Close" />
  </Stack>
);

export const States: Story = () => (
  <Stack gap={3} align="start">
    <Button disabled>Disabled</Button>
    <Button busy>Saving</Button>
    <Button variant="secondary" disabled>
      Disabled secondary
    </Button>
  </Stack>
);

/** A form whose submit button is busy: neither a click nor Enter submits it again. */
export const BusySubmit: Story = () => {
  const [submits, setSubmits] = useState(0);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        setSubmits((n) => n + 1);
      }}
    >
      <Stack gap={3} align="start">
        <TextField label="Note" name="note" value="" onChange={() => undefined} />
        <Button type="submit" busy>
          Saving
        </Button>
        <p data-submits={submits}>Sent {submits} times</p>
      </Stack>
    </form>
  );
};
