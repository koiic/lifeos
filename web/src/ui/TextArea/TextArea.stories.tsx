import type { Story } from '@ladle/react';

import { Stack } from '../Stack';
import { TextArea } from './TextArea';

export default { title: 'TextArea' };

export const States: Story = () => (
  <Stack gap={5}>
    <TextArea
      label="Note"
      name="note"
      value="Slept badly, a bit tired."
      hint="Only you can see this"
      onChange={() => undefined}
    />
    <TextArea
      label="Note"
      name="note-error"
      value=""
      error="Write something or close the sheet"
      onChange={() => undefined}
    />
  </Stack>
);
