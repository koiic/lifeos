import type { Story } from '@ladle/react';

import { Stack } from '../Stack';
import { Icon, iconNames } from './Icon';

export default { title: 'Icon' };

export const All: Story = () => (
  <Stack direction="row" gap={4} wrap>
    {iconNames.map((name) => (
      <Stack key={name} gap={1} align="center">
        <Icon name={name} />
        <span>{name}</span>
      </Stack>
    ))}
  </Stack>
);
