import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { fakeApi } from '../testing/fakeApi';
import {
  deniedSteps,
  enableNotifications,
  type PushEnvironment,
  pushState,
  refreshSubscription,
  sendTestPush,
} from './push';

const KEY = 'GET /api/v1/push/vapid-public-key';
const SAVE = 'POST /api/v1/push/subscriptions';
const TEST = 'POST /api/v1/push/test';

// The server's VAPID public key, and the same bytes as a subscription holds them.
const SERVER_KEY = 'BAECAw';
const SERVER_KEY_BYTES = new Uint8Array([4, 1, 2, 3]).buffer;

const SUBSCRIPTION = {
  options: { applicationServerKey: SERVER_KEY_BYTES },
  unsubscribe: vi.fn().mockResolvedValue(true),
  toJSON: () => ({
    endpoint: 'https://fcm.googleapis.com/fcm/send/abc',
    expirationTime: null,
    keys: { p256dh: 'BPublic', auth: 'secret' },
  }),
};

function environment(overrides: Partial<PushEnvironment> = {}): PushEnvironment {
  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(null),
    subscribe: vi.fn().mockResolvedValue(SUBSCRIPTION),
  };
  return {
    supported: true,
    platform: 'android',
    standalone: false,
    permission: 'default',
    requestPermission: vi.fn().mockResolvedValue('granted'),
    pushManager: () => Promise.resolve(pushManager),
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('[ONB-3] what can be offered (spec 10.6)', () => {
  it('no Push API: unsupported', () => {
    expect(pushState(environment({ supported: false }))).toBe('unsupported');
  });

  it('iPhone in a Safari tab: install first (push works only from the Home Screen)', () => {
    expect(pushState(environment({ platform: 'ios', standalone: false }))).toBe('needs-install');
    expect(pushState(environment({ platform: 'iosOtherBrowser' }))).toBe('needs-install');
    // A Safari tab usually has no Push API at all: still "install first", not "unsupported".
    expect(pushState(environment({ platform: 'ios', standalone: false, supported: false }))).toBe(
      'needs-install',
    );
  });

  it('denied: the steps for where she is (Android app or Chrome tab, iPhone, computer)', () => {
    expect(deniedSteps(environment({ platform: 'android', standalone: true }))).toBe('android');
    expect(deniedSteps(environment({ platform: 'android', standalone: false }))).toBe(
      'androidBrowser',
    );
    expect(deniedSteps(environment({ platform: 'ios', standalone: true }))).toBe('ios');
    expect(deniedSteps(environment({ platform: 'iosOtherBrowser' }))).toBe('ios');
    expect(deniedSteps(environment({ platform: 'other' }))).toBe('other');
  });

  it('iPhone from the Home Screen, or Android: the permission decides', () => {
    expect(pushState(environment({ platform: 'ios', standalone: true }))).toBe('prompt');
    expect(pushState(environment({ permission: 'granted' }))).toBe('granted');
    expect(pushState(environment({ permission: 'denied' }))).toBe('denied');
  });
});

describe('[ONB-3] turning notifications on (from her tap only)', () => {
  it('asks for permission, subscribes with the VAPID key and saves the subscription', async () => {
    const api = fakeApi({ [KEY]: { body: { public_key: 'BServerKey' } }, [SAVE]: { status: 201 } });
    const env = environment();
    const manager = await env.pushManager();
    await expect(enableNotifications(env)).resolves.toBe('granted');
    expect(env.requestPermission).toHaveBeenCalledOnce();
    expect(manager.subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: 'BServerKey',
    });
    expect(api.bodies(SAVE)).toEqual([
      {
        endpoint: 'https://fcm.googleapis.com/fcm/send/abc',
        keys: { p256dh: 'BPublic', auth: 'secret' },
        device_label: copy.notifications.deviceLabel.android,
      },
    ]);
  });

  it('declined: nothing is subscribed or saved', async () => {
    const api = fakeApi({});
    const env = environment({ requestPermission: vi.fn().mockResolvedValue('denied') });
    const manager = await env.pushManager();
    await expect(enableNotifications(env)).resolves.toBe('denied');
    expect(manager.subscribe).not.toHaveBeenCalled();
    expect(api.count(SAVE)).toBe(0);
  });

  it('dismissed without an answer: still asking', async () => {
    fakeApi({});
    const env = environment({ requestPermission: vi.fn().mockResolvedValue('default') });
    await expect(enableNotifications(env)).resolves.toBe('prompt');
  });
});

describe('re-registering on every app start (spec 10.5)', () => {
  it('with permission: saves the current subscription again (the server keeps one row)', async () => {
    const api = fakeApi({ [KEY]: { body: { public_key: SERVER_KEY } }, [SAVE]: { status: 201 } });
    const env = environment({ permission: 'granted' });
    const manager = await env.pushManager();
    vi.mocked(manager.getSubscription).mockResolvedValue(SUBSCRIPTION);
    await refreshSubscription(env);
    expect(manager.subscribe).not.toHaveBeenCalled();
    expect(api.count(SAVE)).toBe(1);
  });

  it('a subscription made with an earlier VAPID key (rotated, spec 15): subscribes anew', async () => {
    const api = fakeApi({ [KEY]: { body: { public_key: SERVER_KEY } }, [SAVE]: { status: 201 } });
    const env = environment({ permission: 'granted' });
    const manager = await env.pushManager();
    const old = {
      ...SUBSCRIPTION,
      options: { applicationServerKey: new Uint8Array([4, 9, 9, 9]).buffer },
      unsubscribe: vi.fn().mockResolvedValue(true),
    };
    vi.mocked(manager.getSubscription).mockResolvedValue(old);
    await refreshSubscription(env);
    expect(old.unsubscribe).toHaveBeenCalledOnce();
    expect(manager.subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: SERVER_KEY,
    });
    expect(api.count(SAVE)).toBe(1);
  });

  it('with permission but no subscription (the browser dropped it): subscribes again', async () => {
    const api = fakeApi({ [KEY]: { body: { public_key: 'BServerKey' } }, [SAVE]: { status: 201 } });
    const env = environment({ permission: 'granted' });
    const manager = await env.pushManager();
    await refreshSubscription(env);
    expect(manager.subscribe).toHaveBeenCalledOnce();
    expect(api.count(SAVE)).toBe(1);
  });

  it('without permission: does nothing (never prompts outside a tap)', async () => {
    const api = fakeApi({});
    const env = environment({ permission: 'default' });
    await refreshSubscription(env);
    expect(env.requestPermission).not.toHaveBeenCalled();
    expect(api.count(SAVE)).toBe(0);
  });
});

describe('[ONB-3] the test push', () => {
  it('asks the server to send it and reports how many devices it reached', async () => {
    const api = fakeApi({ [TEST]: { body: { delivered: 1 } } });
    await expect(sendTestPush()).resolves.toBe(1);
    expect(api.count(TEST)).toBe(1);
  });
});
