import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Card } from './Card';

afterEach(cleanup);

describe('Card', () => {
  it.each(['surface', 'accent', 'fertile', 'sun', 'lilac', 'butter'] as const)(
    '%s card holds its content',
    async (tone) => {
      const { container } = render(
        <Card tone={tone} as="section" labelledBy="t">
          <h2 id="t">Today</h2>
          <p>Body</p>
        </Card>,
      );
      const card = screen.getByRole('region', { name: 'Today' });
      expect(card.dataset.tone).toBe(tone);
      await expectNoAxeViolations(container);
    },
  );

  it('has a Sticker style', () => {
    const { container } = render(<Card sticker>Streak</Card>);
    expect((container.firstElementChild as HTMLElement).dataset.sticker).toBe('true');
  });
});
