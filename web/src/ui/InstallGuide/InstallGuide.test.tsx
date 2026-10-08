import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { InstallGuide } from './InstallGuide';

afterEach(cleanup);

const steps = [
  { icon: 'share', text: 'Tap the Share button' },
  { icon: 'addToHome', text: 'Tap Add to Home Screen' },
  { icon: 'home', text: 'Open Life OS from your Home Screen' },
] as const;

describe('[ONB-1] InstallGuide (spec 5.5): numbered steps with illustrations', () => {
  it('lists the steps in order, each with a decorative illustration', async () => {
    const { container } = render(
      <InstallGuide
        label="Steps"
        steps={steps}
        continueLabel="Not now"
        onContinue={() => undefined}
      />,
    );
    const list = screen.getByRole('list', { name: 'Steps' });
    expect(list.tagName).toBe('OL');
    const items = screen.getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual(steps.map((step) => step.text));
    for (const item of items) {
      expect(item.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    }
    await expectNoAxeViolations(container);
  });

  it('can be dismissed', () => {
    const onContinue = vi.fn();
    render(
      <InstallGuide label="Steps" steps={steps} continueLabel="Not now" onContinue={onContinue} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(onContinue).toHaveBeenCalledOnce();
  });

  it('shows an optional note', () => {
    render(
      <InstallGuide
        label="Steps"
        steps={steps}
        note="Use the Home Screen icon from now on."
        continueLabel="Not now"
        onContinue={() => undefined}
      />,
    );
    expect(screen.getByText('Use the Home Screen icon from now on.')).toBeDefined();
  });

  it('keeps its list semantics in Safari (list-style: none drops them without a role)', () => {
    render(
      <InstallGuide
        label="Steps"
        steps={steps}
        continueLabel="Not now"
        onContinue={() => undefined}
      />,
    );
    expect(screen.getByRole('list', { name: 'Steps' }).getAttribute('role')).toBe('list');
  });
});
