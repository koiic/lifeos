import { cleanup, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { MoreScreen } from './MoreScreen';

afterEach(cleanup);

describe('the More tab (spec 5.1)', () => {
  it('leads to Settings (the other entries arrive with their screens)', async () => {
    const { container } = renderRoute(<MoreScreen />, { path: '/more', url: '/more' });
    expect(screen.getByRole('heading', { level: 1, name: copy.more.title })).toBeDefined();
    expect(screen.getByRole('link', { name: copy.more.settings }).getAttribute('href')).toBe(
      '/settings',
    );
    await expectNoAxeViolations(container);
  });
});
