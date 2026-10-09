import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { deniedSteps, enableNotifications, pushState, sendTestPush } from '../../lib/push/push';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { NotificationsScreen } from './NotificationsScreen';

vi.mock('../../lib/push/push', async (original) => ({
  ...(await original<typeof import('../../lib/push/push')>()),
  pushState: vi.fn(),
  enableNotifications: vi.fn(),
  sendTestPush: vi.fn(),
  deniedSteps: vi.fn(() => 'ios'),
}));

const t = copy.notifications;

function open() {
  return renderRoute(<NotificationsScreen />, {
    path: '/setup/notifications',
    url: '/setup/notifications',
  });
}

beforeEach(() => {
  vi.mocked(pushState).mockReturnValue('prompt');
  vi.mocked(enableNotifications).mockResolvedValue('granted');
  vi.mocked(sendTestPush).mockResolvedValue(1);
});

afterEach(() => {
  cleanup();
  vi.mocked(pushState).mockReset();
  vi.mocked(enableNotifications).mockReset();
  vi.mocked(sendTestPush).mockReset();
});

describe('[ONB-3] notifications opt-in (/setup/notifications)', () => {
  it('asks for nothing until she taps; then turns them on and sends a test', async () => {
    const { container } = open();
    expect(enableNotifications).not.toHaveBeenCalled();
    await expectNoAxeViolations(container);
    fireEvent.click(screen.getByRole('button', { name: t.enable }));
    expect(enableNotifications).toHaveBeenCalledOnce();
    expect(await screen.findByText(t.testSent)).toBeDefined();
    expect(sendTestPush).toHaveBeenCalledOnce();
    expect(screen.getByRole('region', { name: t.granted.title })).toBeDefined();
  });

  it('declined at the prompt: explains how to turn them on again', async () => {
    vi.mocked(enableNotifications).mockResolvedValue('denied');
    open();
    fireEvent.click(screen.getByRole('button', { name: t.enable }));
    expect(await screen.findByRole('region', { name: t.denied.title })).toBeDefined();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      ...t.denied.steps.ios,
    ]);
    expect(sendTestPush).not.toHaveBeenCalled();
  });

  it('already denied: the steps, and no button that cannot work', () => {
    vi.mocked(pushState).mockReturnValue('denied');
    open();
    expect(screen.getByRole('region', { name: t.denied.title })).toBeDefined();
    expect(screen.queryByRole('button', { name: t.enable })).toBeNull();
  });

  it('denied in an Android Chrome tab: the browser steps, not the app ones', () => {
    vi.mocked(pushState).mockReturnValue('denied');
    vi.mocked(deniedSteps).mockReturnValueOnce('androidBrowser');
    open();
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      ...t.denied.steps.androidBrowser,
    ]);
  });

  it('iPhone in a Safari tab: install first, with the way to the guide', () => {
    vi.mocked(pushState).mockReturnValue('needs-install');
    open();
    expect(screen.getByRole('region', { name: t.needsInstall.title })).toBeDefined();
    expect(screen.getByRole('link', { name: t.needsInstall.action }).getAttribute('href')).toBe(
      '/install',
    );
    expect(screen.queryByRole('button', { name: t.enable })).toBeNull();
  });

  it('already on: offers a test notification', async () => {
    vi.mocked(pushState).mockReturnValue('granted');
    open();
    fireEvent.click(screen.getByRole('button', { name: t.sendTest }));
    expect(await screen.findByText(t.testSent)).toBeDefined();
  });

  it('a test that reached no device says so', async () => {
    vi.mocked(pushState).mockReturnValue('granted');
    vi.mocked(sendTestPush).mockResolvedValue(0);
    open();
    fireEvent.click(screen.getByRole('button', { name: t.sendTest }));
    expect(await screen.findByText(t.testFailed)).toBeDefined();
  });

  it('offline when sending the test: says the connection, not her phone', async () => {
    vi.mocked(pushState).mockReturnValue('granted');
    vi.mocked(sendTestPush).mockRejectedValue(new TypeError('Failed to fetch'));
    open();
    fireEvent.click(screen.getByRole('button', { name: t.sendTest }));
    expect(await screen.findByText(copy.common.networkError)).toBeDefined();
  });

  it('offline when turning them on: says the connection', async () => {
    vi.mocked(enableNotifications).mockRejectedValue(new TypeError('Failed to fetch'));
    open();
    fireEvent.click(screen.getByRole('button', { name: t.enable }));
    expect(await screen.findByText(copy.common.networkError)).toBeDefined();
  });

  it('this browser cannot: says so, and she can carry on', async () => {
    vi.mocked(pushState).mockReturnValue('unsupported');
    open();
    expect(screen.getByRole('region', { name: t.unsupported.title })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: t.continue }));
    await waitFor(() => expect(screen.getByTestId('arrived').textContent).toBe('/today'));
  });

  it('arriving moves focus to the heading', () => {
    open();
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: t.title }));
  });
});
