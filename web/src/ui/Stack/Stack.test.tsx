import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Stack } from './Stack';

afterEach(cleanup);

describe('Stack (layout primitive, plan 5.2)', () => {
  it('stacks its children in the requested element', async () => {
    const { container } = render(
      <Stack as="ul" gap={4}>
        <li>One</li>
        <li>Two</li>
      </Stack>,
    );
    const list = screen.getByRole('list');
    expect(list.tagName).toBe('UL');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(list.dataset.gap).toBe('4');
    await expectNoAxeViolations(container);
  });

  it('defaults to a vertical div with the base gap', () => {
    const { container } = render(<Stack>text</Stack>);
    const div = container.firstElementChild as HTMLElement;
    expect(div.tagName).toBe('DIV');
    expect(div.dataset.direction).toBe('column');
    expect(div.dataset.gap).toBe('4');
  });

  it('lays out a row', () => {
    const { container } = render(
      <Stack direction="row" gap={2} align="center" justify="between">
        <span>a</span>
      </Stack>,
    );
    const div = container.firstElementChild as HTMLElement;
    expect(div.dataset.direction).toBe('row');
    expect(div.dataset.align).toBe('center');
    expect(div.dataset.justify).toBe('between');
  });

  it('can be the page itself: a main landmark with page padding', () => {
    const { container } = render(
      <Stack as="main" inset="page">
        <p>Content</p>
      </Stack>,
    );
    const main = container.querySelector('main');
    expect(main).not.toBeNull();
    expect(main?.dataset.inset).toBe('page');
  });

  it('has no inset by default', () => {
    const { container } = render(
      <Stack>
        <p>Content</p>
      </Stack>,
    );
    expect((container.firstElementChild as HTMLElement).dataset.inset).toBe('none');
  });
});
