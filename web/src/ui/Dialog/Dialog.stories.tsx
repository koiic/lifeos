import type { Story } from '@ladle/react';

import { Button } from '../Button';
import { Dialog } from './Dialog';

export default { title: 'Dialog' };

export const Confirmation: Story = () => (
  <Dialog
    open
    alert
    title="Delete this note?"
    description="You can't undo this."
    onClose={() => undefined}
    actions={
      <>
        <Button variant="secondary">Keep</Button>
        <Button variant="danger">Delete note</Button>
      </>
    }
  />
);

export const Plain: Story = () => (
  <Dialog
    open
    title="Install Life OS"
    onClose={() => undefined}
    actions={<Button>Got it</Button>}
  />
);
