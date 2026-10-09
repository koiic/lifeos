import { describe, expect, it, vi } from 'vitest';

import { handleClick, handlePush, handleSubscriptionChange, type WindowLike } from './push';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const DOSE = {
  reminder_id: '0192f2aa-0000-7000-8000-000000000001',
  kind: 'medication',
  title: 'Vitamin D',
  body: '1 tablet — tap when taken',
  url: '/meds/doses/0192f2bb',
  tag: 'dose:0192f2bb',
  actions: [
    { action: 'taken', title: 'Taken' },
    { action: 'snooze', title: 'In 15 min' },
  ],
  badge_count: 2,
};

function json(body: unknown): string {
  return JSON.stringify(body);
}

describe('[ONB-3] push (spec 10.5): always a visible notification', () => {
  it('shows the message with its data, actions and the app icon, then sets the badge', async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined);
    const setAppBadge = vi.fn().mockResolvedValue(undefined);
    await handlePush(json(DOSE), { showNotification, setAppBadge });
    expect(showNotification).toHaveBeenCalledWith('Vitamin D', {
      body: '1 tablet — tap when taken',
      tag: 'dose:0192f2bb',
      data: { url: '/meds/doses/0192f2bb', reminder_id: DOSE.reminder_id, kind: 'medication' },
      actions: DOSE.actions,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
    });
    expect(setAppBadge).toHaveBeenCalledWith(2);
    expect(showNotification.mock.invocationCallOrder[0]).toBeLessThan(
      setAppBadge.mock.invocationCallOrder[0] ?? 0,
    );
  });

  it('where the badge API is missing, the notification still shows', async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined);
    await handlePush(json(DOSE), { showNotification });
    expect(showNotification).toHaveBeenCalledOnce();
  });

  it('a test push (no reminder, no actions, no badge) shows and leaves the badge alone', async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined);
    const setAppBadge = vi.fn();
    await handlePush(
      json({
        reminder_id: null,
        kind: 'test',
        title: 'Notifications are on',
        body: "You'll get reminders here",
        url: '/today',
        tag: 'test',
        actions: [],
        badge_count: null,
      }),
      { showNotification, setAppBadge },
    );
    expect(showNotification).toHaveBeenCalledWith('Notifications are on', {
      body: "You'll get reminders here",
      tag: 'test',
      data: { url: '/today', reminder_id: null, kind: 'test' },
      actions: [],
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
    });
    expect(setAppBadge).not.toHaveBeenCalled();
  });

  it('an unreadable push still shows a neutral notification (iOS needs one for every push)', async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined);
    await handlePush('not json', { showNotification });
    await handlePush(null, { showNotification });
    expect(showNotification).toHaveBeenNthCalledWith(1, 'Life OS', {
      body: 'You have a reminder',
      tag: 'life-os',
      data: { url: '/today', reminder_id: null, kind: 'unknown' },
      actions: [],
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
    });
    expect(showNotification).toHaveBeenCalledTimes(2);
  });

  it.each([
    'https://evil.example/x',
    '//evil.example/x',
    '/\\evil.example/x',
    '/\t/evil.example/x',
    '/\n/evil.example/x',
    '/\r/evil.example/x',
    'javascript:alert(1)',
    '/.//evil.example',
    '/a/..//evil.example',
    '/%2e//evil.example',
    '/..//evil.example/x',
    '/./\\evil.example',
  ])('never another site, however the url is written: %j', async (url) => {
    const showNotification = vi.fn().mockResolvedValue(undefined);
    await handlePush(json({ ...DOSE, url }), { showNotification });
    expect(showNotification.mock.calls[0]?.[1]).toMatchObject({ data: { url: '/today' } });
  });

  it('an app path keeps its query and fragment', async () => {
    const showNotification = vi.fn().mockResolvedValue(undefined);
    await handlePush(json({ ...DOSE, url: '/meds/doses/1?from=push#top' }), { showNotification });
    expect(showNotification.mock.calls[0]?.[1]).toMatchObject({
      data: { url: '/meds/doses/1?from=push#top' },
    });
  });
});

function windows(...urls: string[]) {
  const clients = urls.map((url) => ({
    url: `https://app.test${url}`,
    focus: vi.fn().mockResolvedValue(undefined),
    navigate: vi.fn().mockResolvedValue(undefined),
  }));
  return { clients, matchAll: vi.fn().mockResolvedValue(clients as unknown as WindowLike[]) };
}

const dataOf = { url: DOSE.url, reminder_id: DOSE.reminder_id, kind: 'medication' };

describe('[ONB-3] notification click (spec 10.5)', () => {
  it('"Taken" marks the dose taken, once (Idempotency-Key = the reminder), without opening the app', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    const openWindow = vi.fn();
    const { clients, matchAll } = windows('/today');
    await handleClick({ action: 'taken', data: dataOf }, { fetch, openWindow, matchAll });
    expect(clients[0]?.focus).not.toHaveBeenCalled(); // an open app is left where it is
    expect(clients[0]?.navigate).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith('/api/v1/medication-doses/0192f2bb/taken', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-LifeOS-Client': 'web', 'Idempotency-Key': DOSE.reminder_id },
    });
    expect(openWindow).not.toHaveBeenCalled();
  });

  it.each([
    ['the server refuses', () => Promise.resolve(new Response(null, { status: 401 }))],
    ['there is no connection', () => Promise.reject(new TypeError('offline'))],
  ])('"Taken" when %s: opens the dose screen instead', async (_case, reply) => {
    const fetch = vi.fn(reply);
    const openWindow = vi.fn().mockResolvedValue(null);
    const { matchAll } = windows();
    await handleClick({ action: 'taken', data: dataOf }, { fetch, openWindow, matchAll });
    expect(openWindow).toHaveBeenCalledWith('/meds/doses/0192f2bb');
  });

  it('"Taken" on a notification that is not a dose opens it instead of posting', async () => {
    const fetch = vi.fn();
    const openWindow = vi.fn().mockResolvedValue(null);
    const { matchAll } = windows();
    await handleClick(
      { action: 'taken', data: { ...dataOf, url: '/appointments/1' } },
      { fetch, openWindow, matchAll },
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(openWindow).toHaveBeenCalledWith('/appointments/1');
  });

  it.each([
    ['the server refuses', () => Promise.resolve(new Response(null, { status: 409 }))],
    ['there is no connection', () => Promise.reject(new TypeError('offline'))],
  ])('"In 15 min" when %s: opens the reminder instead', async (_case, reply) => {
    const fetch = vi.fn(reply);
    const openWindow = vi.fn().mockResolvedValue(null);
    const { matchAll } = windows();
    await handleClick({ action: 'snooze', data: dataOf }, { fetch, openWindow, matchAll });
    expect(openWindow).toHaveBeenCalledWith('/meds/doses/0192f2bb');
  });

  it('"In 15 min" snoozes the reminder', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    const openWindow = vi.fn();
    const { matchAll } = windows();
    await handleClick({ action: 'snooze', data: dataOf }, { fetch, openWindow, matchAll });
    expect(fetch).toHaveBeenCalledWith(`/api/v1/reminders/${DOSE.reminder_id}/snooze`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-LifeOS-Client': 'web',
        // Spec 9.1: the key is a UUID (a fresh one for this tap).
        'Idempotency-Key': expect.stringMatching(UUID),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ preset: '15m' }),
    });
    expect(openWindow).not.toHaveBeenCalled();
  });

  it('a tap on the notification focuses an open app window and takes it to the url', async () => {
    const fetch = vi.fn();
    const openWindow = vi.fn();
    const { clients, matchAll } = windows('/today');
    await handleClick({ action: '', data: dataOf }, { fetch, openWindow, matchAll });
    expect(clients[0]?.focus).toHaveBeenCalled();
    expect(clients[0]?.navigate).toHaveBeenCalledWith('/meds/doses/0192f2bb');
    expect(openWindow).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('with no app window open, opens one at the url', async () => {
    const openWindow = vi.fn().mockResolvedValue(null);
    const { matchAll } = windows();
    await handleClick({ action: '', data: dataOf }, { fetch: vi.fn(), openWindow, matchAll });
    expect(openWindow).toHaveBeenCalledWith('/meds/doses/0192f2bb');
  });

  it.each([
    '//evil.example/x',
    '/\t/evil.example/x',
    '/\n/evil.example/x',
    '/.//evil.example',
    '/a/..//evil.example',
  ])('never navigates to another site: %j', async (url) => {
    const openWindow = vi.fn().mockResolvedValue(null);
    const { matchAll } = windows();
    await handleClick(
      { action: '', data: { ...dataOf, url } },
      { fetch: vi.fn(), openWindow, matchAll },
    );
    expect(openWindow).toHaveBeenCalledWith('/today');
  });
});

describe('pushsubscriptionchange (spec 10.5): resubscribe and tell the server', () => {
  it('subscribes again with the VAPID key and saves the new subscription', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ public_key: 'BKey' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 201 }));
    const subscription = {
      toJSON: () => ({
        // As browsers give it: expirationTime too, which the server does not take.
        endpoint: 'https://fcm.googleapis.com/x',
        expirationTime: null,
        keys: { p256dh: 'B', auth: 'a' },
      }),
    };
    const subscribe = vi.fn().mockResolvedValue(subscription);
    await handleSubscriptionChange({ fetch, subscribe });
    expect(fetch.mock.calls[0]?.[0]).toBe('/api/v1/push/vapid-public-key');
    expect(subscribe).toHaveBeenCalledWith({ userVisibleOnly: true, applicationServerKey: 'BKey' });
    expect(fetch.mock.calls[1]).toEqual([
      '/api/v1/push/subscriptions',
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-LifeOS-Client': 'web', 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: 'https://fcm.googleapis.com/x',
          keys: { p256dh: 'B', auth: 'a' },
        }),
      },
    ]);
  });

  it('signed out (401): gives up quietly; the app re-registers on its next start', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));
    const subscribe = vi.fn();
    await expect(handleSubscriptionChange({ fetch, subscribe })).resolves.toBeUndefined();
    expect(subscribe).not.toHaveBeenCalled();
  });
});
