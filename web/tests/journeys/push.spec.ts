import { generateKeyPairSync, randomBytes } from 'node:crypto';
import { createServer, type IncomingHttpHeaders, type Server } from 'node:http';

import { expect, test } from '@playwright/test';

import { copy } from '../../src/copy/en-GB';
import { addAuthenticator, registerWithPasskey } from './session';
import { createInvite, WEB_ORIGIN } from './stack';

/**
 * T14 (ONB-3, spec 10.4, 10.5) on the real local stack. Headless Chromium has no real push
 * service, so: the test push goes from the API to a fake push service run by this test (allowed
 * only with ENV=local), and the service worker's push handler is driven through Chrome's
 * DevTools protocol. The real phone check is the manual step in T14's done-when.
 */

const t = copy.notifications;

// The full Chromium ("new headless"): the default headless shell has no notifications at all.
test.use({ channel: 'chromium' });

interface Received {
  path: string;
  headers: IncomingHttpHeaders;
  bytes: number;
}

async function fakePushService(): Promise<{ server: Server; port: number; received: Received[] }> {
  const received: Received[] = [];
  const server = createServer((request, response) => {
    let bytes = 0;
    request.on('data', (chunk: Buffer) => (bytes += chunk.length));
    request.on('end', () => {
      received.push({ path: request.url ?? '', headers: request.headers, bytes });
      response.writeHead(201).end();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const port = typeof address === 'object' && address !== null ? address.port : 0;
  return { server, port, received };
}

/** A browser's subscription keys: an uncompressed P-256 point and a 16-byte auth secret. */
function subscriptionKeys() {
  const { publicKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
  const jwk = publicKey.export({ format: 'jwk' });
  const point = Buffer.concat([
    Buffer.from([4]),
    Buffer.from(jwk.x ?? '', 'base64url'),
    Buffer.from(jwk.y ?? '', 'base64url'),
  ]);
  return { p256dh: point.toString('base64url'), auth: randomBytes(16).toString('base64url') };
}

test.describe('Web Push (ONB-3)', () => {
  test('[ONB-3] she taps "Turn on", allows, and the test push reaches her device', async ({
    page,
  }) => {
    const email = 'zee.push@example.test';
    const push = await fakePushService();
    try {
      // The browser's side, as it would be on her phone: the permission prompt answers Allow,
      // and the push service is the fake one (headless Chromium has none). Spec 15 allows push
      // permission to be mocked; everything after the browser (API, VAPID, encryption) is real.
      const endpoint = `http://127.0.0.1:${String(push.port)}/s/phone`;
      await page.addInitScript(
        ({ endpoint, keys }) => {
          let permission: NotificationPermission = 'default';
          Object.defineProperty(Notification, 'permission', { get: () => permission });
          Notification.requestPermission = () => Promise.resolve((permission = 'granted'));
          let current: unknown = null;
          PushManager.prototype.getSubscription = () => Promise.resolve(current as null);
          PushManager.prototype.subscribe = (options) => {
            const key = String(options?.applicationServerKey);
            const raw = atob(key.replace(/-/g, '+').replace(/_/g, '/'));
            current = {
              endpoint,
              options: {
                applicationServerKey: Uint8Array.from(raw, (c) => c.charCodeAt(0)).buffer,
              },
              unsubscribe: () => Promise.resolve(true),
              toJSON: () => ({ endpoint, expirationTime: null, keys }),
            };
            (window as unknown as { subscribedWith: string }).subscribedWith = key;
            return Promise.resolve(current as PushSubscription);
          };
        },
        { endpoint, keys: subscriptionKeys() },
      );
      await addAuthenticator(page);
      await registerWithPasskey(page, createInvite(email), email);

      await page.goto('/setup/notifications');
      const prompt = page.getByRole('region', { name: t.prompt.title });
      await expect(prompt).toBeVisible();
      await prompt.getByRole('button', { name: t.enable }).click();

      const card = page.getByRole('region', { name: t.granted.title });
      await expect(card.getByRole('status')).toHaveText(t.testSent);
      // Subscribed with the server's VAPID key, and the push was signed with it.
      const vapid = await page.request.get('/api/v1/push/vapid-public-key');
      const { public_key: key } = (await vapid.json()) as { public_key: string };
      expect(
        await page.evaluate(() => (window as unknown as { subscribedWith: string }).subscribedWith),
      ).toBe(key);

      const [delivered] = push.received.filter((r) => r.path === '/s/phone');
      expect(delivered).toBeDefined();
      expect(delivered?.headers['ttl']).toBe('86400');
      expect(delivered?.headers['urgency']).toBe('normal');
      expect(delivered?.headers['content-encoding']).toBe('aes128gcm');
      expect(delivered?.headers['authorization']).toMatch(new RegExp(`^vapid t=[^,]+, ?k=${key}$`));
      expect(delivered?.bytes).toBeGreaterThan(0);
    } finally {
      push.server.close();
    }
  });

  test('[ONB-3] the service worker shows a push as a notification (spec 10.5)', async ({
    page,
    context,
  }) => {
    await context.grantPermissions(['notifications'], { origin: WEB_ORIGIN });
    await page.goto('/install');
    await page.evaluate(() => navigator.serviceWorker.ready);
    // Headless Chromium has no notification centre: a shown notification is dropped within half
    // a second, too soon to find it reliably with getNotifications(). So record what the real
    // service worker passes to showNotification (10.5) and still let it show.
    const [worker] = context.serviceWorkers();
    if (worker === undefined) throw new Error('no service worker');
    await worker.evaluate(() => {
      const scope = self as unknown as ServiceWorkerGlobalScope & {
        shown: unknown[];
        badges: number[];
      };
      const show = scope.registration.showNotification.bind(scope.registration);
      scope.shown = [];
      scope.badges = [];
      scope.registration.showNotification = (title, options) => {
        const data = options?.data as { url?: string; reminder_id?: string; kind?: string };
        scope.shown.push({
          title,
          body: options?.body,
          tag: options?.tag,
          data,
          actions: (options as { actions?: unknown[] } | undefined)?.actions,
          icon: options?.icon,
          badge: options?.badge,
        });
        return show(title, options);
      };
      Object.defineProperty(scope.navigator, 'setAppBadge', {
        value: (count: number) => {
          scope.badges.push(count);
          return Promise.resolve();
        },
      });
    });
    const cdp = await context.newCDPSession(page);
    const registration = new Promise<string>((resolve) => {
      cdp.on('ServiceWorker.workerRegistrationUpdated', ({ registrations }) => {
        const ours = registrations.find((r) => r.scopeURL === `${WEB_ORIGIN}/` && !r.isDeleted);
        if (ours !== undefined) resolve(ours.registrationId);
      });
    });
    await cdp.send('ServiceWorker.enable');
    const registrationId = await registration;
    const message = JSON.stringify({
      reminder_id: '0192f2aa-0000-7000-8000-000000000001',
      kind: 'medication',
      title: 'Vitamin D',
      body: '1 tablet — tap when taken',
      url: '/meds/doses/0192f2aa',
      tag: 'dose:0192f2aa',
      actions: [
        { action: 'taken', title: 'Taken' },
        { action: 'snooze', title: 'In 15 min' },
      ],
      badge_count: 2,
    });
    await cdp.send('ServiceWorker.deliverPushMessage', {
      origin: WEB_ORIGIN,
      registrationId,
      data: message,
    });
    await expect
      .poll(() => worker.evaluate(() => (self as unknown as { shown: unknown[] }).shown))
      .toEqual([
        {
          title: 'Vitamin D',
          body: '1 tablet — tap when taken',
          tag: 'dose:0192f2aa',
          data: {
            url: '/meds/doses/0192f2aa',
            reminder_id: '0192f2aa-0000-7000-8000-000000000001',
            kind: 'medication',
          },
          actions: [
            { action: 'taken', title: 'Taken' },
            { action: 'snooze', title: 'In 15 min' },
          ],
          icon: '/icons/icon-192.png',
          badge: '/icons/icon-192.png',
        },
      ]);
    // Then the app badge (10.5).
    await expect
      .poll(() => worker.evaluate(() => (self as unknown as { badges: number[] }).badges))
      .toEqual([2]);
  });
});
