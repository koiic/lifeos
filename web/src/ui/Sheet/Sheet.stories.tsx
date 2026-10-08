import type { Story } from '@ladle/react';
import { useState } from 'react';

import { Button } from '../Button';
import { TextField } from '../TextField';
import { Sheet } from './Sheet';

export default { title: 'Sheet' };

export const Open: Story = () => {
  const [open, setOpen] = useState(true);
  return (
    <Sheet open={open} title="Check-in" closeLabel="Close" onClose={() => setOpen(false)}>
      <TextField label="How are you feeling?" name="mood" value="" onChange={() => undefined} />
      <Button>Save check-in</Button>
    </Sheet>
  );
};
