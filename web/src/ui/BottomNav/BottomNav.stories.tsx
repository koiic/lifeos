import type { Story } from '@ladle/react';
import { MemoryRouter } from 'react-router-dom';

import { BottomNav } from './BottomNav';

export default { title: 'BottomNav' };

export const TodayCurrent: Story = () => (
  <MemoryRouter initialEntries={['/today']}>
    <BottomNav
      label="Main"
      items={[
        { to: '/today', label: 'Today', icon: 'home' },
        { to: '/health', label: 'Health', icon: 'droplet' },
        { to: '/calendar', label: 'Calendar', icon: 'calendar' },
        { to: '/more', label: 'More', icon: 'more' },
      ]}
      action={{ label: 'Add', onPress: () => undefined }}
    />
  </MemoryRouter>
);
