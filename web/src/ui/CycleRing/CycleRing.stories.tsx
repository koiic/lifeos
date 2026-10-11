import type { Story } from '@ladle/react';

import { Stack } from '../Stack';
import { CycleRing, MiniRing } from './CycleRing';

export default { title: 'CycleRing' };

/** Spec 8.4 State: On period */
export const OnPeriod: Story = () => (
  <CycleRing cycleLength={28} periodDays={5} today={2} phase="menstrual" state="on_period" />
);

/** Spec 8.4 State: Upcoming period */
export const Upcoming: Story = () => (
  <CycleRing
    cycleLength={28}
    periodDays={5}
    fertileStart={12}
    fertileEnd={17}
    today={20}
    phase="luteal"
    state="upcoming"
  />
);

/** Spec 8.4 State: Fertile window */
export const FertileWindow: Story = () => (
  <CycleRing
    cycleLength={28}
    periodDays={5}
    fertileStart={12}
    fertileEnd={17}
    today={14}
    phase="fertile_window"
    state="window"
  />
);

/** Spec 8.4 State: Expected period window */
export const Window: Story = () => (
  <CycleRing
    cycleLength={28}
    periodDays={5}
    fertileStart={12}
    fertileEnd={17}
    today={27}
    phase="luteal"
    state="window"
  />
);

/** Spec 8.4 State: Late period */
export const Late: Story = () => (
  <CycleRing cycleLength={28} periodDays={5} today={32} state="late" />
);

/** Spec 8.4 State: Long gap (>90 days) */
export const LongGap: Story = () => (
  <CycleRing cycleLength={28} periodDays={5} today={95} state="long_gap" />
);

/** Spec 8.4 State: Irregular cycles */
export const Irregular: Story = () => (
  <CycleRing
    cycleLength={35}
    periodDays={6}
    fertileStart={15}
    fertileEnd={22}
    today={18}
    phase="fertile_window"
    state="irregular"
  />
);

/** Spec 8.4 State: Waiting (postpartum mode) */
export const Waiting: Story = () => <CycleRing cycleLength={28} state="waiting" />;

/** Spec 8.4 State: No data */
export const NoData: Story = () => <CycleRing cycleLength={28} state="no_data" />;

/** Mini ring for Today screen */
export const Mini: Story = () => (
  <Stack direction="row" gap={3}>
    <MiniRing cycleLength={28} periodDays={5} today={2} />
    <MiniRing cycleLength={28} periodDays={5} fertileStart={12} fertileEnd={17} today={14} />
    <MiniRing cycleLength={28} periodDays={5} today={24} />
  </Stack>
);
