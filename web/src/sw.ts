/// <reference lib="webworker" />
// Spec 11.3: the service worker (vite-plugin-pwa, injectManifest). Push and notification handlers
// (10.5) are added by T14.
import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';

import { networkThenShell } from './lib/sw/navigation';

declare const self: ServiceWorkerGlobalScope;

// The app shell, route chunks, fonts and icons, revisioned by the build.
precacheAndRoute(self.__WB_MANIFEST);

// Navigations: the network with a 3 s timeout, else the precached index.html (the app shell).
// No copy of a page is kept: page URLs can carry single-use invite or recovery tokens (12.3),
// which must not end up in Cache Storage. API requests are never cached here (11.4).
const shell = createHandlerBoundToURL('/index.html');
registerRoute(
  new NavigationRoute(
    (options) =>
      networkThenShell(
        (signal) => fetch(options.request, { signal }),
        () => shell(options),
      ),
    { denylist: [/^\/api\//] },
  ),
);

// The update toast's "Refresh" (registerType 'prompt'): activate the waiting version now. Only
// the app's own windows can ask; otherwise it activates by itself on the next cold start.
self.addEventListener('message', (event) => {
  const fromWindow = event.source instanceof WindowClient;
  if (fromWindow && (event.data as { type?: unknown } | null)?.type === 'SKIP_WAITING') {
    void self.skipWaiting();
  }
});
