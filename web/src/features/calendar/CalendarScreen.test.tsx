import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { CalendarScreen } from './CalendarScreen';

afterEach(cleanup);

describe('the Calendar tab (spec 5.1), until its screens arrive', () => {
  it('names the tab and says what will be here', async () => {
    const { container } = render(<CalendarScreen />);
    expect(screen.getByRole('heading', { level: 1, name: copy.calendar.title })).toBeDefined();
    expect(screen.getByText(copy.calendar.empty)).toBeDefined();
    await expectNoAxeViolations(container);
  });
});
