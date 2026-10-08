import type { Story } from '@ladle/react';
import { useState } from 'react';

import { Select } from './Select';

export default { title: 'Select' };

export const Theme: Story = () => {
  const [theme, setTheme] = useState<'system' | 'light' | 'dark'>('system');
  return (
    <Select
      label="Theme"
      name="theme"
      value={theme}
      hint="Match device follows your phone's setting"
      options={[
        { value: 'system', label: 'Match device' },
        { value: 'light', label: 'Sorbet' },
        { value: 'dark', label: 'Night Garden' },
      ]}
      onChange={setTheme}
    />
  );
};

export const WithError: Story = () => (
  <Select
    label="Reminder"
    name="reminder"
    value="none"
    error="Choose when to be reminded"
    options={[
      { value: 'none', label: 'No reminder' },
      { value: 'day', label: 'The day before' },
    ]}
    onChange={() => undefined}
  />
);
