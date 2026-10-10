import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as offlineModule from '../../lib/offline';
import { fakeApi, problem } from '../../lib/testing/fakeApi';
import { meBody } from '../../lib/testing/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { TodayScreen } from './TodayScreen';

const t = copy.today;
const ME = 'GET /api/v1/me';
const PROFILE = 'PATCH /api/v1/me';

function open() {
  return renderRoute(<TodayScreen />, { path: '/today', url: '/today' });
}

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers({ toFake: ['Date'] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('[TOD-1] Today greets her by her local time, with the date', () => {
  it.each([
    ['2026-10-08T06:30:00Z', t.greeting.morning],
    ['2026-10-08T12:30:00Z', t.greeting.afternoon],
    ['2026-10-08T17:30:00Z', t.greeting.evening],
    ['2026-10-08T22:30:00Z', t.greeting.night],
  ])('at %s UTC (BST in London) she reads "%s, Zee"', async (now, greeting) => {
    vi.setSystemTime(new Date(now));
    fakeApi({ [ME]: { body: meBody() } });
    open();
    expect(
      await screen.findByRole('heading', { level: 1, name: t.greetingWithName(greeting, 'Zee') }),
    ).toBeDefined();
  });

  it('uses her profile timezone for both, not the device (en-GB date)', async () => {
    vi.setSystemTime(new Date('2026-10-08T23:30:00Z'));
    fakeApi({ [ME]: { body: meBody({ profile: { timezone: 'Asia/Tokyo' } }) } });
    const { container } = open();
    expect(
      await screen.findByRole('heading', { name: t.greetingWithName(t.greeting.morning, 'Zee') }),
    ).toBeDefined();
    expect(screen.getByText('Friday 9 October')).toBeDefined();
    await expectNoAxeViolations(container);
  });

  it('shows a placeholder while loading and a retry when /me fails', async () => {
    vi.setSystemTime(new Date('2026-10-08T08:00:00Z'));
    const api = fakeApi({ [ME]: [problem(503, 'down'), { body: meBody() }] });
    open();
    expect(screen.getByLabelText(copy.common.loading)).toBeDefined();
    fireEvent.click(await screen.findByRole('button', { name: copy.common.retry }));
    expect(await screen.findByRole('heading', { level: 1 })).toBeDefined();
    expect(api.count(ME)).toBe(2);
  });
});

describe('[SET-1] her phone is in another timezone (spec 11.7, CR-030)', () => {
  const lagos = meBody({ device_timezone: 'Africa/Lagos', timezone_differs: true });

  it('offers to switch, and switching saves the device timezone with her version', async () => {
    vi.setSystemTime(new Date('2026-10-08T08:00:00Z'));
    const api = fakeApi({
      [ME]: { body: lagos },
      [PROFILE]: { body: { ...lagos.profile, timezone: 'Africa/Lagos', version: 'p2' } },
    });
    open();
    expect(await screen.findByRole('region', { name: t.timezone.title('Lagos') })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: t.timezone.switch('Lagos') }));
    await waitFor(() => expect(api.bodies(PROFILE)).toEqual([{ timezone: 'Africa/Lagos' }]));
    expect(api.headers(PROFILE)[0]?.get('If-Match')).toBe('"p1"');
    expect(await screen.findByText(t.timezone.switched('Lagos'))).toBeDefined();
    expect(screen.queryByRole('region', { name: t.timezone.title('Lagos') })).toBeNull();
  });

  it('keeping her timezone hides the prompt on this device for that zone', async () => {
    vi.setSystemTime(new Date('2026-10-08T08:00:00Z'));
    const api = fakeApi({ [ME]: { body: lagos } });
    open();
    fireEvent.click(await screen.findByRole('button', { name: t.timezone.keep }));
    expect(screen.queryByRole('region', { name: t.timezone.title('Lagos') })).toBeNull();
    cleanup();
    open();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', { name: t.timezone.title('Lagos') })).toBeNull();
    expect(api.count(PROFILE)).toBe(0);
  });

  it('no prompt when the timezones agree', async () => {
    vi.setSystemTime(new Date('2026-10-08T08:00:00Z'));
    fakeApi({ [ME]: { body: meBody({ device_timezone: 'Europe/London' }) } });
    open();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('button', { name: t.timezone.keep })).toBeNull();
  });
});

describe('[TOD-7] sync status: pending offline changes shown as "Will sync" chip', () => {
  it('displays "Will sync" chip while outbox is non-empty and triggers sync on tap', async () => {
    vi.setSystemTime(new Date('2026-10-08T08:00:00Z'));
    fakeApi({ [ME]: { body: meBody() } });
    const mockSyncNow = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(offlineModule, 'useSync').mockReturnValue({
      pendingCount: 2,
      isSyncing: false,
      isPaused: false,
      lastSyncedAt: null,
      lastError: null,
      syncNow: mockSyncNow,
    });

    const { container } = open();
    await screen.findByRole('heading', { level: 1 });

    const syncBtn = screen.getByRole('button', { name: t.willSync });
    expect(syncBtn).toBeDefined();

    fireEvent.click(syncBtn);
    expect(mockSyncNow).toHaveBeenCalledOnce();

    await expectNoAxeViolations(container);
  });

  it('hides "Will sync" chip when outbox is empty', async () => {
    vi.setSystemTime(new Date('2026-10-08T08:00:00Z'));
    fakeApi({ [ME]: { body: meBody() } });
    vi.spyOn(offlineModule, 'useSync').mockReturnValue({
      pendingCount: 0,
      isSyncing: false,
      isPaused: false,
      lastSyncedAt: null,
      lastError: null,
      syncNow: vi.fn(),
    });

    open();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('button', { name: t.willSync })).toBeNull();
  });
});
