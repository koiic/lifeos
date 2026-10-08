import { type ChildProcess, spawn } from 'node:child_process';
import { appendFileSync, cpSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, type Page, test } from '@playwright/test';

import { manifest } from '../../pwa.manifest.ts';
import { copy } from '../../src/copy/en-GB';

/**
 * T13 done-when (CR-026): Chrome reports the app installable; the offline shell loads; the
 * install guide shows only when not standalone. Spec 11.2 manifest, 11.3 service worker, ONB-1.
 */

/** Wait until the service worker controls the page (the second load after installing it). */
async function controlled(page: Page, path: string) {
  await page.goto(path);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect
    .poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null))
    .toBe(true);
}

test.describe('PWA (spec 11.2, 11.3)', () => {
  test('[ONB-1] Chrome reports the app installable', async ({ page }) => {
    await controlled(page, '/install');
    const cdp = await page.context().newCDPSession(page);
    // Chrome's own installability verdict. On its own it is not enough: current Chrome reports
    // no errors even for a page without a manifest (any site can be installed as a shortcut), so
    // the criteria Lighthouse's installable audit checked are asserted on Chrome's parsed manifest.
    const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
    expect(installabilityErrors).toEqual([]);
    const parsed = await cdp.send('Page.getAppManifest');
    expect(parsed.url).toMatch(/\/manifest\.webmanifest$/);
    expect(parsed.errors).toEqual([]);
    const manifest = JSON.parse(parsed.data ?? '{}') as {
      name?: string;
      start_url?: string;
      display?: string;
      icons?: { src: string; sizes: string; type: string }[];
    };
    expect(manifest.name).toBe('Life OS');
    expect(manifest.start_url).toBe('/today?source=pwa');
    expect(manifest.display).toBe('standalone');
    const sizes = (manifest.icons ?? []).map((icon) => icon.sizes);
    expect(sizes).toEqual(expect.arrayContaining(['192x192', '512x512']));
    for (const icon of manifest.icons ?? []) {
      const response = await page.request.get(icon.src);
      expect(response.status(), icon.src).toBe(200);
      expect(response.headers()['content-type'], icon.src).toBe('image/png');
    }
    expect(await page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
  });

  test('[ONB-1] serves the spec 11.2 manifest and the apple-touch-icon', async ({ page }) => {
    await page.goto('/install');
    const href = await page.locator('link[rel="manifest"]').getAttribute('href');
    const served = (await (await page.request.get(href ?? '')).json()) as unknown;
    // Exactly spec 11.2: nothing added by the build tooling.
    expect(served).toEqual(manifest);
    const touch = await page.locator('link[rel="apple-touch-icon"]').getAttribute('href');
    expect((await page.request.get(touch ?? '')).headers()['content-type']).toBe('image/png');
  });

  test('the shell loads offline, and API responses are never cached', async ({ page, context }) => {
    await controlled(page, '/signin');
    // An API call while online, through the controlling service worker…
    expect(await page.evaluate(async () => (await fetch('/api/v1/healthz')).status)).toBe(200);
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByRole('heading', { name: copy.auth.signIn.title })).toBeVisible();
    // Another route's chunk was precached too.
    await page.goto('/install');
    await expect(page.getByRole('heading', { name: copy.install.title })).toBeVisible();
    const cached = await page.evaluate(async () => {
      const urls: string[] = [];
      for (const name of await caches.keys()) {
        for (const request of await (await caches.open(name)).keys()) urls.push(request.url);
      }
      return urls;
    });
    expect(cached.length).toBeGreaterThan(0);
    // …left nothing in the caches, so offline it fails rather than answering from a cache.
    expect(cached.filter((url) => new URL(url).pathname.startsWith('/api/'))).toEqual([]);
    const offline = await page.evaluate(async () => {
      try {
        return (await fetch('/api/v1/healthz')).status;
      } catch {
        return 'failed';
      }
    });
    expect(offline).toBe('failed');
    await context.setOffline(false);
  });

  test('pages are never stored: no invite or recovery token is left in the caches', async ({
    page,
  }) => {
    await controlled(page, '/signin');
    await page.goto('/register?token=secret-invite-token');
    await page.goto('/recover?token=secret-recovery-token');
    await page.goto('/signin');
    const stored = await page.evaluate(async () => {
      const names = await caches.keys();
      const urls: string[] = [];
      for (const name of names) {
        for (const request of await (await caches.open(name)).keys()) urls.push(request.url);
      }
      return { names, urls };
    });
    // Only the build's precache (revisioned files, no query strings): spec 11.3's fallback is
    // the precached index.html, so no runtime copy of a page is kept.
    expect(stored.names).toHaveLength(1);
    expect(stored.names[0]).toMatch(/^workbox-precache/);
    expect(stored.urls.filter((url) => url.includes('token'))).toEqual([]);
  });

  test('[ONB-1] in a browser tab the guide shows the steps for this platform', async ({ page }) => {
    await page.goto('/install');
    await expect(page.getByRole('heading', { name: copy.install.title })).toBeVisible();
    const steps = page.getByRole('list', { name: copy.install.stepsLabel }).getByRole('listitem');
    await expect(steps).toHaveText([...copy.install.steps.android]); // the Pixel 7 profile
  });

  test('[ONB-1] opened from the Home Screen (standalone): no guide', async ({ page }) => {
    await page.addInitScript(() => {
      const real = window.matchMedia.bind(window);
      window.matchMedia = (query: string) =>
        query === '(display-mode: standalone)'
          ? ({ ...real(query), matches: true, media: query } as MediaQueryList)
          : real(query);
    });
    await page.goto('/install');
    await expect(page).not.toHaveURL(/\/install/);
    await expect(page.getByRole('heading', { name: copy.install.title })).toHaveCount(0);
  });

  test('a new version waits for her: the toast offers it, Refresh activates it (11.3)', async ({
    browser,
  }) => {
    // Its own copy of the build on its own origin, so changing sw.js disturbs no other test.
    const web = fileURLToPath(new URL('../..', import.meta.url));
    const port = 4176;
    const origin = `http://localhost:${String(port)}`;
    const servers: ChildProcess[] = [];
    const dirs: string[] = [];
    const up = async () => (await fetch(`${origin}/install`).catch(() => null))?.status ?? 0;

    const serve = async (dir: string) => {
      // Vite itself (not through npx), so stopping it stops the server; tracked for cleanup.
      const server = spawn(
        process.execPath,
        [
          join(web, 'node_modules/vite/bin/vite.js'),
          'preview',
          '--outDir',
          dir,
          '--host',
          'localhost',
          '--port',
          String(port),
          '--strictPort',
        ],
        { cwd: web, stdio: 'ignore' },
      );
      servers.push(server);
      await expect.poll(up, { timeout: 20_000 }).toBe(200);
    };
    const stopAll = async () => {
      for (const server of servers) server.kill();
      await expect.poll(up, { timeout: 15_000 }).toBe(0);
    };

    // Nothing may be listening there already (a leftover server would answer for ours).
    expect(await up()).toBe(0);
    const context = await browser.newContext({ baseURL: origin });
    try {
      const [v1, v2] = ['lifeos-v1-', 'lifeos-v2-'].map((prefix) => {
        const dir = mkdtempSync(join(tmpdir(), prefix));
        dirs.push(dir);
        cpSync(join(web, 'dist'), dir, { recursive: true });
        return dir;
      });
      appendFileSync(join(v2 ?? '', 'sw.js'), '\n// the next version\n');
      const page = await context.newPage();

      await serve(v1 ?? '');
      await controlled(page, '/install');
      await expect(page.getByText(copy.update.ready)).toHaveCount(0);

      // The next deploy: the browser finds a changed sw.js.
      await stopAll();
      await serve(v2 ?? '');
      await page.evaluate(async () => {
        await (await navigator.serviceWorker.getRegistration())?.update();
      });

      // It waits (registerType 'prompt': no taking over by itself) and the toast offers it.
      const toast = page.getByRole('status').filter({ hasText: copy.update.ready });
      await expect(toast).toBeVisible();
      expect(
        await page.evaluate(async () =>
          Boolean((await navigator.serviceWorker.getRegistration())?.waiting),
        ),
      ).toBe(true);

      // Refresh: the waiting version takes over (controllerchange) and the page reloads on it.
      await page.evaluate(() => {
        navigator.serviceWorker.addEventListener('controllerchange', () => {
          sessionStorage.setItem('lifeos.test.controllerchange', 'yes');
        });
      });
      await Promise.all([
        page.waitForEvent('load'),
        toast.getByRole('button', { name: copy.update.refresh }).click(),
      ]);
      expect(
        await page.evaluate(() => sessionStorage.getItem('lifeos.test.controllerchange')),
      ).toBe('yes');
      await expect
        .poll(() =>
          page.evaluate(async () => {
            const registration = await navigator.serviceWorker.getRegistration();
            return registration?.waiting === null && navigator.serviceWorker.controller !== null;
          }),
        )
        .toBe(true);
      await expect(page.getByText(copy.update.ready)).toHaveCount(0);
    } finally {
      await context.close();
      await stopAll();
      for (const dir of dirs) rmSync(dir, { recursive: true, force: true });
    }
  });
});
