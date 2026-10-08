import type { Story } from '@ladle/react';

import { Card } from '../Card';
import { CodeList } from './CodeList';

export default { title: 'CodeList' };

const codes = [
  'k7qp-2mzd',
  'x9fh-4rtc',
  'b3nw-8vjy',
  'm6ds-1qke',
  'p2lc-7gxa',
  'h8tz-5wnr',
  'f4yb-9cme',
  'r1vk-6dpu',
  'w5gj-3hsq',
  'c0ux-2ylf',
];

export const RecoveryCodes: Story = () => (
  <Card>
    <CodeList
      label="Recovery codes"
      codes={codes}
      copyLabel="Copy codes"
      copiedLabel="Codes copied"
      copyFailedLabel="Couldn't copy the codes."
    />
  </Card>
);
