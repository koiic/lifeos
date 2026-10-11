import { cleanup, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { SettingsScreen } from './SettingsScreen';

const t = copy.settingsHome;

afterEach(cleanup);

describe('Settings (spec 5.2 /settings/*, ONB-2, SET-4)', () => {
  it('[ONB-2][SET-4] lists profile, theme, health mode, security, notifications, and setup wizard', async () => {
    const { container } = renderRoute(<SettingsScreen />, { path: '/settings', url: '/settings' });
    expect(screen.getByRole('heading', { level: 1, name: t.title })).toBeDefined();
    const links = screen
      .getAllByRole('link')
      .map((link) => [link.textContent, link.getAttribute('href')]);
    expect(links).toEqual([
      [t.profile, '/settings/profile'],
      [t.theme, '/settings/theme'],
      [t.healthMode, '/settings/mode'],
      [t.security, '/settings/security'],
      [t.notifications, '/setup/notifications'],
      [t.setupWizard, '/setup/1'],
    ]);
    await expectNoAxeViolations(container);
  });
});
