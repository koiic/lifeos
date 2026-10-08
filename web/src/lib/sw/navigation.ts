// Spec 11.3: how the service worker answers a navigation. Pure (the fetch and the shell are
// passed in), so the timing is unit-tested; src/sw.ts wires it to Workbox.

/** How long a navigation waits for the network before the cached shell (11.3). */
export const NAVIGATION_TIMEOUT_MS = 3000;

/**
 * The network's answer if it comes within the timeout — whatever its status, so the server's own
 * redirects and error pages reach the browser — otherwise (offline, or too slow: the request is
 * aborted) the cached app shell. Nothing is cached here.
 */
export async function networkThenShell(
  fetchPage: (signal: AbortSignal) => Promise<Response>,
  shell: () => Promise<Response>,
  timeoutMs: number = NAVIGATION_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<'timeout'>((resolve) => {
    timer = setTimeout(() => {
      controller.abort();
      resolve('timeout');
    }, timeoutMs);
  });
  try {
    const result = await Promise.race([fetchPage(controller.signal), timeout]);
    return result === 'timeout' ? await shell() : result;
  } catch {
    return shell();
  } finally {
    clearTimeout(timer);
  }
}
