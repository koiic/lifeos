import { cleanup, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { SettingsScreen } from './SettingsScreen';

const t = copy.settingsHome;

afterEach(cleanup);

describe('Settings (spec 5.2 /settings/*)', () => {
  it('lists profile, theme, security and notifications', async () => {
    const { container } = renderRoute(<SettingsScreen />, { path: '/settings', url: '/settings' });
    expect(screen.getByRole('heading', { level: 1, name: t.title })).toBeDefined();
    const links = screen
      .getAllByRole('link')
      .map((link) => [link.textContent, link.getAttribute('href')]);
    expect(links).toEqual([
      [t.profile, '/settings/profile'],
      [t.theme, '/settings/theme'],
      [t.security, '/settings/security'],
      [t.notifications, '/setup/notifications'],
    ]);
    await expectNoAxeViolations(container);
  });
});
