/**
 * Cloudflare Pages Function API Proxy (spec 14.1, ADR-0001, CR-006).
 *
 * Forwards `/api/*` requests to `ORIGIN_URL` with Cloudflare Access service-token
 * headers (`CF-Access-Client-Id`, `CF-Access-Client-Secret`), preserving method,
 * query parameters, headers, cookies, and body without extra logic.
 */

export interface ProxyEnv {
  ORIGIN_URL?: string;
  CF_ACCESS_CLIENT_ID?: string;
  CF_ACCESS_CLIENT_SECRET?: string;
}

export async function handleProxy(request: Request, env: ProxyEnv): Promise<Response> {
  const originUrl = env.ORIGIN_URL;
  if (!originUrl) {
    return new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Proxy misconfigured: ORIGIN_URL is not set',
        status: 502,
      }),
      {
        status: 502,
        headers: { 'content-type': 'application/problem+json' },
      },
    );
  }

  let targetOrigin: URL;
  try {
    targetOrigin = new URL(originUrl);
  } catch {
    return new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Proxy misconfigured: invalid ORIGIN_URL',
        status: 502,
      }),
      {
        status: 502,
        headers: { 'content-type': 'application/problem+json' },
      },
    );
  }

  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(incomingUrl.pathname + incomingUrl.search, targetOrigin);

  const headers = new Headers(request.headers);
  headers.delete('host');

  if (env.CF_ACCESS_CLIENT_ID) {
    headers.set('CF-Access-Client-Id', env.CF_ACCESS_CLIENT_ID);
  }
  if (env.CF_ACCESS_CLIENT_SECRET) {
    headers.set('CF-Access-Client-Secret', env.CF_ACCESS_CLIENT_SECRET);
  }

  const init: RequestInit & { duplex?: 'half' } = {
    method: request.method,
    headers,
    redirect: 'manual',
  };

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = request.body;
    init.duplex = 'half';
  }

  try {
    return await fetch(targetUrl.toString(), init);
  } catch (error) {
    return new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Upstream service unavailable',
        status: 502,
        detail: error instanceof Error ? error.message : String(error),
      }),
      {
        status: 502,
        headers: { 'content-type': 'application/problem+json' },
      },
    );
  }
}
