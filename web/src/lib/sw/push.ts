// Spec 10.5: what the service worker does with a push, a notification click and a changed
// subscription. Pure (the worker's APIs are passed in), so it is unit-tested; src/sw.ts wires it.

const ICON = '/icons/icon-192.png';
const HOME = '/today';
const CLIENT_HEADER = { 'X-LifeOS-Client': 'web' } as const;

/** What `notification.data` carries (10.5). */
export interface NotificationData {
  url: string;
  reminder_id: string | null;
  kind: string;
}

interface Action {
  action: string;
  title: string;
}

export interface ShowOptions {
  body: string;
  tag: string;
  data: NotificationData;
  actions: Action[];
  icon: string;
  badge: string;
}

// A placeholder origin: a path resolves onto it, anything that leaves it is another site.
const BASE = 'https://app.invalid';

/** An app path only: a push or click can never send her to another site. The url is resolved
 * the way the browser will (tabs and newlines dropped, backslashes as slashes), then checked. */
function samePath(url: unknown): string {
  if (typeof url !== 'string' || !url.startsWith('/')) return HOME;
  try {
    const resolved = new URL(url, BASE);
    const path = resolved.pathname + resolved.search + resolved.hash;
    // Dot segments can leave "//host" (e.g. "/.//evil.example"): the browser would read that as
    // another site, so a resolved path must start with exactly one slash.
    return resolved.origin === BASE && !path.startsWith('//') ? path : HOME;
  } catch {
    return HOME;
  }
}

function parse(raw: string | null): Record<string, unknown> | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' && value !== '' ? value : fallback;
}

function actions(value: unknown): Action[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (a): a is Action =>
      typeof a === 'object' &&
      a !== null &&
      typeof (a as Action).action === 'string' &&
      typeof (a as Action).title === 'string',
  );
}

/**
 * `push`: always a visible notification (iOS requires one for every push), even when the
 * message cannot be read; then the app badge where supported.
 */
export async function handlePush(
  raw: string | null,
  worker: {
    showNotification: (title: string, options: ShowOptions) => Promise<void>;
    setAppBadge?: ((count: number) => Promise<void>) | undefined;
  },
): Promise<void> {
  const message = parse(raw);
  const reminder = message?.['reminder_id'];
  const options: ShowOptions = {
    body: text(message?.['body'], 'You have a reminder'),
    tag: text(message?.['tag'], 'life-os'),
    data: {
      url: samePath(message?.['url']),
      reminder_id: typeof reminder === 'string' ? reminder : null,
      kind: text(message?.['kind'], 'unknown'),
    },
    actions: actions(message?.['actions']),
    icon: ICON,
    badge: ICON,
  };
  await worker.showNotification(text(message?.['title'], 'Life OS'), options);
  const badge = message?.['badge_count'];
  if (typeof badge === 'number' && worker.setAppBadge !== undefined) {
    await worker.setAppBadge(badge);
  }
}

export interface WindowLike {
  url: string;
  focus: () => Promise<unknown>;
  navigate: (url: string) => Promise<unknown>;
}

interface ClickWorker {
  fetch: (input: string, init: RequestInit) => Promise<Response>;
  openWindow: (url: string) => Promise<unknown>;
  matchAll: () => Promise<readonly WindowLike[]>;
}

async function call(worker: ClickWorker, url: string, init: RequestInit): Promise<boolean> {
  try {
    return (await worker.fetch(url, init)).ok;
  } catch {
    return false;
  }
}

/** The dose id from its screen's path (`/meds/doses/{id}`), for the "Taken" action. */
function doseId(url: string): string | null {
  return /^\/meds\/doses\/([^/?#]+)$/.exec(url)?.[1] ?? null;
}

async function show(worker: ClickWorker, url: string): Promise<void> {
  const [open] = await worker.matchAll();
  if (open !== undefined) {
    await open.focus();
    await open.navigate(url);
    return;
  }
  await worker.openWindow(url);
}

/**
 * `notificationclick`: "Taken" marks the dose taken (once: the reminder is the idempotency key)
 * and "In 15 min" snoozes it, without opening the app; if that fails, or on a plain tap, the app
 * opens (or comes forward) at the notification's screen.
 */
export async function handleClick(
  click: { action: string; data: unknown },
  worker: ClickWorker,
): Promise<void> {
  const data = (
    typeof click.data === 'object' && click.data !== null ? click.data : {}
  ) as Partial<NotificationData>;
  const url = samePath(data.url);
  const reminder = typeof data.reminder_id === 'string' ? data.reminder_id : null;

  if (click.action === 'taken' && reminder !== null) {
    const dose = doseId(url);
    const done =
      dose !== null &&
      (await call(worker, `/api/v1/medication-doses/${encodeURIComponent(dose)}/taken`, {
        method: 'POST',
        credentials: 'include',
        headers: { ...CLIENT_HEADER, 'Idempotency-Key': reminder },
      }));
    if (!done) await show(worker, url);
    return;
  }
  if (click.action === 'snooze' && reminder !== null) {
    const done = await call(worker, `/api/v1/reminders/${encodeURIComponent(reminder)}/snooze`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        ...CLIENT_HEADER,
        'Idempotency-Key': crypto.randomUUID(), // spec 9.1: a UUID
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ preset: '15m' }),
    });
    if (!done) await show(worker, url);
    return;
  }
  await show(worker, url);
}

export interface SubscriptionBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  device_label?: string;
}

/** The server's subscription body (9.2) from a browser's `subscription.toJSON()`: the endpoint
 * and keys only (browsers add `expirationTime`, which the server does not take). */
export function subscriptionBody(json: unknown, deviceLabel?: string): SubscriptionBody {
  const value = (typeof json === 'object' && json !== null ? json : {}) as {
    endpoint?: unknown;
    keys?: { p256dh?: unknown; auth?: unknown };
  };
  return {
    endpoint: typeof value.endpoint === 'string' ? value.endpoint : '',
    keys: {
      p256dh: typeof value.keys?.p256dh === 'string' ? value.keys.p256dh : '',
      auth: typeof value.keys?.auth === 'string' ? value.keys.auth : '',
    },
    ...(deviceLabel === undefined ? {} : { device_label: deviceLabel }),
  };
}

/**
 * `pushsubscriptionchange`: subscribe again with the server's VAPID key and save it. Signed out
 * or offline it gives up; the app re-registers on its next start (10.5).
 */
export async function handleSubscriptionChange(worker: {
  fetch: (input: string, init?: RequestInit) => Promise<Response>;
  subscribe: (options: {
    userVisibleOnly: boolean;
    applicationServerKey: string;
  }) => Promise<{ toJSON: () => unknown }>;
}): Promise<void> {
  try {
    const keyResponse = await worker.fetch('/api/v1/push/vapid-public-key', {
      credentials: 'include',
      headers: CLIENT_HEADER,
    });
    if (!keyResponse.ok) return;
    const { public_key: key } = (await keyResponse.json()) as { public_key: string };
    const subscription = await worker.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    });
    await worker.fetch('/api/v1/push/subscriptions', {
      method: 'POST',
      credentials: 'include',
      headers: { ...CLIENT_HEADER, 'Content-Type': 'application/json' },
      body: JSON.stringify(subscriptionBody(subscription.toJSON())),
    });
  } catch {
    // Offline or refused: the next app start re-registers.
  }
}
