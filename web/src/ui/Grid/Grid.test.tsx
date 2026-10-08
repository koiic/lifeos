import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Grid } from './Grid';

afterEach(cleanup);

describe('Grid (layout primitive, plan 5.2)', () => {
  it('lays children out in columns with a token gap', async () => {
    const { container } = render(
      <Grid columns={2} gap={3}>
        <p>a</p>
        <p>b</p>
      </Grid>,
    );
    const grid = container.firstElementChild as HTMLElement;
    expect(grid.dataset.columns).toBe('2');
    expect(grid.dataset.gap).toBe('3');
    expect(grid.children).toHaveLength(2);
    await expectNoAxeViolations(container);
  });
});
