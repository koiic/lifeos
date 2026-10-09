import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { NotificationPermissionCard } from './NotificationPermissionCard';

afterEach(cleanup);

describe('[ONB-3] NotificationPermissionCard (spec 5.5)', () => {
  it('a labelled card with one action', async () => {
    const onClick = vi.fn();
    const { container } = render(
      <NotificationPermissionCard
        state="prompt"
        title="Turn on reminders"
        body="We'll ask your phone for permission."
        action={{ label: 'Turn on notifications', onClick }}
      />,
    );
    expect(screen.getByRole('region', { name: 'Turn on reminders' })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Turn on notifications' }));
    expect(onClick).toHaveBeenCalledOnce();
    await expectNoAxeViolations(container);
  });

  it('the action is a native button in the tab order (Enter and Space work)', () => {
    render(
      <NotificationPermissionCard
        state="prompt"
        title="Turn on reminders"
        body="We'll ask your phone for permission."
        action={{ label: 'Turn on notifications', onClick: vi.fn() }}
      />,
    );
    const button = screen.getByRole('button', { name: 'Turn on notifications' });
    button.focus();
    expect(document.activeElement).toBe(button);
    expect(button.tagName).toBe('BUTTON');
    expect(button.tabIndex).toBe(0);
  });

  it('denied: the steps to turn them back on, in order', async () => {
    const { container } = render(
      <NotificationPermissionCard
        state="denied"
        title="Notifications are off"
        body="To turn them on:"
        steps={{ label: 'How to turn them on', items: ['Open Settings', 'Tap Notifications'] }}
      />,
    );
    const list = screen.getByRole('list', { name: 'How to turn them on' });
    expect(list.tagName).toBe('OL');
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Open Settings',
      'Tap Notifications',
    ]);
    expect(screen.queryByRole('button')).toBeNull();
    await expectNoAxeViolations(container);
  });

  it('shows the state as data for styling and a status message', async () => {
    const { container } = render(
      <NotificationPermissionCard
        state="granted"
        title="Notifications are on"
        body="Send one to check."
        status="Sent. Check your phone."
      />,
    );
    const card = screen.getByRole('region', { name: 'Notifications are on' });
    expect(card.contains(container.querySelector('[data-state="granted"]'))).toBe(true);
    expect(screen.getByRole('status').textContent).toBe('Sent. Check your phone.');
    await expectNoAxeViolations(container);
  });

  it('unsupported: says so, with nothing to press', async () => {
    const { container } = render(
      <NotificationPermissionCard
        state="unsupported"
        title="This browser can't show notifications"
        body="Everything is still in the app."
      />,
    );
    expect(
      screen.getByRole('region', { name: "This browser can't show notifications" }),
    ).toBeDefined();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
    await expectNoAxeViolations(container);
  });

  it('a link action goes somewhere (the install guide)', async () => {
    const { container } = render(
      <NotificationPermissionCard
        state="needs-install"
        title="Add Life OS to your Home Screen first"
        body="iPhone sends notifications only to apps on the Home Screen."
        action={{ label: 'How to add it', href: '/install' }}
      />,
    );
    expect(screen.getByRole('link', { name: 'How to add it' }).getAttribute('href')).toBe(
      '/install',
    );
    await expectNoAxeViolations(container);
  });
});
