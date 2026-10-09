// Web Push on this device (spec 10.5, 10.6, ONB-3): what can be offered, turning it on from her
// tap, re-registering on every app start, and the test push.
import { copy } from '../../copy/en-GB';
import { api } from '../api';
import { currentPlatform, isStandalone, type Platform } from '../install/install';
import { subscriptionBody } from '../sw/push';

/** What the opt-in can offer here. */
export type PushState = 'unsupported' | 'needs-install' | 'prompt' | 'granted' | 'denied';

interface BrowserSubscription {
  options?: { applicationServerKey: ArrayBuffer | null };
  unsubscribe?: () => Promise<boolean>;
  toJSON: () => unknown;
}

interface PushManagerLike {
  getSubscription: () => Promise<BrowserSubscription | null>;
  subscribe: (options: {
    userVisibleOnly: boolean;
    applicationServerKey: string;
  }) => Promise<BrowserSubscription>;
}

/** The browser's push APIs, injectable for tests. */
export interface PushEnvironment {
  supported: boolean;
  platform: Platform;
  standalone: boolean;
  permission: NotificationPermission;
  requestPermission: () => Promise<NotificationPermission>;
  pushManager: () => Promise<PushManagerLike>;
}

const DEVICE_LABEL: Record<Platform, string> = {
  ...copy.notifications.deviceLabel,
  iosOtherBrowser: copy.notifications.deviceLabel.ios,
};

/** Which "how to allow them again" steps fit where she is (ONB-3; 10.6: Android pushes in a
 * Chrome tab too, where there is no app icon to hold). Other iOS browsers never get here. */
export function deniedSteps(
  env: PushEnvironment = browserEnvironment(),
): 'ios' | 'android' | 'androidBrowser' | 'other' {
  if (env.platform === 'ios' || env.platform === 'iosOtherBrowser') return 'ios';
  if (env.platform === 'android') return env.standalone ? 'android' : 'androidBrowser';
  return 'other';
}

export function browserEnvironment(): PushEnvironment {
  const supported =
    typeof window !== 'undefined' &&
    'Notification' in window &&
    'PushManager' in window &&
    'serviceWorker' in navigator;
  return {
    supported,
    platform: currentPlatform(),
    standalone: isStandalone(),
    permission: supported ? Notification.permission : 'denied',
    requestPermission: () => Notification.requestPermission(),
    pushManager: async () => (await navigator.serviceWorker.ready).pushManager,
  };
}

/** 10.6: on iPhone, push works only from the Home Screen app; elsewhere the permission decides. */
export function pushState(env: PushEnvironment = browserEnvironment()): PushState {
  if (env.platform === 'iosOtherBrowser' || (env.platform === 'ios' && !env.standalone)) {
    return 'needs-install';
  }
  if (!env.supported) return 'unsupported';
  if (env.permission === 'granted') return 'granted';
  if (env.permission === 'denied') return 'denied';
  return 'prompt';
}

async function save(env: PushEnvironment, subscription: BrowserSubscription): Promise<void> {
  await api.request(
    'POST',
    '/api/v1/push/subscriptions',
    subscriptionBody(subscription.toJSON(), DEVICE_LABEL[env.platform]),
  );
}

async function serverKey(): Promise<string> {
  return (await api.request('GET', '/api/v1/push/vapid-public-key')).public_key;
}

async function subscribe(env: PushEnvironment, key?: string): Promise<BrowserSubscription> {
  const applicationServerKey = key ?? (await serverKey());
  const manager = await env.pushManager();
  return manager.subscribe({ userVisibleOnly: true, applicationServerKey });
}

/** Unpadded base64url, as the server writes its VAPID public key. */
function b64url(bytes: ArrayBuffer): string {
  let binary = '';
  for (const byte of new Uint8Array(bytes)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * ONB-3: call only from her tap (iOS refuses a permission request without one). Asks, then
 * subscribes and saves the subscription. Returns the permission she chose.
 */
export async function enableNotifications(
  env: PushEnvironment = browserEnvironment(),
): Promise<'granted' | 'denied' | 'prompt'> {
  const permission = await env.requestPermission();
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'prompt';
  await save(env, await subscribe(env));
  return 'granted';
}

/**
 * 10.5: on every app start, with permission already given, save this device's subscription
 * again (the server keeps one row per endpoint), subscribing anew if the browser dropped it.
 * Never asks for permission.
 */
export async function refreshSubscription(
  env: PushEnvironment = browserEnvironment(),
): Promise<void> {
  if (pushState(env) !== 'granted') return;
  const manager = await env.pushManager();
  const key = await serverKey();
  let subscription = await manager.getSubscription();
  const subscribedKey = subscription?.options?.applicationServerKey;
  if (subscription !== null && subscribedKey && b64url(subscribedKey) !== key) {
    // Made with an earlier VAPID key (rotated, spec 15): its pushes would all be refused.
    await subscription.unsubscribe?.();
    subscription = null;
  }
  await save(env, subscription ?? (await subscribe(env, key)));
}

/** ONB-3: the 10.7 test push to her devices; how many it reached. */
export async function sendTestPush(): Promise<number> {
  const result = await api.request('POST', '/api/v1/push/test');
  return result.delivered;
}
