import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Icon, iconNames } from './Icon';

afterEach(cleanup);

describe('Icon (plan 5.2: 24 px grid, 2 px stroke, currentColor)', () => {
  it.each(iconNames)('%s is a decorative 24 px stroke icon', (name) => {
    const { container } = render(<Icon name={name} />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    expect(svg?.getAttribute('focusable')).toBe('false');
    expect(svg?.getAttribute('stroke')).toBe('currentColor');
    expect(svg?.getAttribute('stroke-width')).toBe('2');
    expect(svg?.getAttribute('fill')).toBe('none');
    expect(svg?.querySelectorAll('path, circle, rect, line, polyline').length).toBeGreaterThan(0);
  });

  it('has a small size', () => {
    const { container } = render(<Icon name="check" size="sm" />);
    expect(container.querySelector('svg')?.dataset.size).toBe('sm');
  });

  it('is ignored by assistive technology inside a labelled control', async () => {
    const { container } = render(
      <button type="button" aria-label="Close">
        <Icon name="close" />
      </button>,
    );
    await expectNoAxeViolations(container);
  });
});
