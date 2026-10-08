import type { Story } from '@ladle/react';

import { copy } from '../../copy/en-GB';
import { InstallGuide, type InstallStep } from './InstallGuide';

export default { title: 'InstallGuide' };

const t = copy.install;

function steps(texts: readonly string[], icons: readonly InstallStep['icon'][]) {
  return texts.map((text, i) => ({ text, icon: icons[i] ?? 'home' }));
}

const noop = () => undefined;

export const Iphone: Story = () => (
  <InstallGuide
    label={t.stepsLabel}
    steps={steps(t.steps.ios, ['share', 'addToHome', 'home'])}
    note={t.note}
    continueLabel={t.continue}
    onContinue={noop}
  />
);

export const Android: Story = () => (
  <InstallGuide
    label={t.stepsLabel}
    steps={steps(t.steps.android, ['menu', 'addToHome', 'home'])}
    note={t.note}
    continueLabel={t.continue}
    onContinue={noop}
  />
);

export const Other: Story = () => (
  <InstallGuide
    label={t.stepsLabel}
    steps={steps(t.steps.other, ['menu', 'addToHome', 'home'])}
    note={t.note}
    continueLabel={t.continue}
    onContinue={noop}
  />
);
