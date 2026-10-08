import type { Story } from '@ladle/react';

import { Stack } from '../Stack';
import { DateTimePicker } from './DateTimePicker';

export default { title: 'DateTimePicker' };

export const Kinds: Story = () => (
  <Stack gap={5}>
    <DateTimePicker
      label="Date"
      name="date"
      kind="date"
      value="2026-10-08"
      onChange={() => undefined}
    />
    <DateTimePicker label="Time" name="time" kind="time" value="19:00" onChange={() => undefined} />
    <DateTimePicker
      label="Appointment"
      name="when"
      kind="datetime-local"
      value="2026-10-14T14:30"
      error="Pick a time in the future"
      onChange={() => undefined}
    />
  </Stack>
);
