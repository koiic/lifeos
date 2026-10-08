import type { Story } from '@ladle/react';

import { FAB } from './FAB';

export default { title: 'FAB' };

export const Add: Story = () => <FAB label="Add" onClick={() => undefined} />;
