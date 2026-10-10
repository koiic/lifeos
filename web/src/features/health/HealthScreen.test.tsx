import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { HealthScreen } from './HealthScreen';

afterEach(cleanup);

describe('the Health tab (spec 5.1), until its screens arrive', () => {
  it('names the tab and says what will be here', async () => {
    const { container } = render(<HealthScreen />);
    expect(screen.getByRole('heading', { level: 1, name: copy.health.title })).toBeDefined();
    expect(screen.getByText(copy.health.empty)).toBeDefined();
    await expectNoAxeViolations(container);
  });
});
