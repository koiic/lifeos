import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { handleProxy, type ProxyEnv } from '../../functions/api/proxy';

describe('Cloudflare Pages Function API Proxy (spec 14.1, ADR-0001)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns 502 problem+json when ORIGIN_URL is missing', async () => {
    const request = new Request('https://app.example.com/api/v1/healthz');
    const env: ProxyEnv = {};

    const response = await handleProxy(request, env);
    expect(response.status).toBe(502);
    expect(response.headers.get('content-type')).toBe('application/problem+json');
    const body = (await response.json()) as { title: string; status: number };
    expect(body.status).toBe(502);
    expect(body.title).toContain('ORIGIN_URL');
  });

  it('forwards method, path, query parameters, and headers to ORIGIN_URL', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    globalThis.fetch = mockFetch;

    const request = new Request('https://app.example.com/api/v1/today?date=2026-10-10', {
      method: 'GET',
      headers: {
        accept: 'application/json',
        cookie: 'session=xyz123',
        'x-custom': 'test-header',
      },
    });

    const env: ProxyEnv = {
      ORIGIN_URL: 'https://origin.internal:8000',
    };

    const response = await handleProxy(request, env);
    expect(response.status).toBe(200);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [targetUrl, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(targetUrl).toBe('https://origin.internal:8000/api/v1/today?date=2026-10-10');
    expect(init.method).toBe('GET');

    const sentHeaders = new Headers(init.headers);
    expect(sentHeaders.get('accept')).toBe('application/json');
    expect(sentHeaders.get('cookie')).toBe('session=xyz123');
    expect(sentHeaders.get('x-custom')).toBe('test-header');
    expect(sentHeaders.has('cf-access-client-id')).toBe(false);
  });

  it('injects Cloudflare Access service token headers when configured in env', async () => {
    const mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    globalThis.fetch = mockFetch;

    const request = new Request('https://app.example.com/api/v1/me', {
      method: 'PATCH',
      headers: {
        'content-type': 'application/json',
        'if-match': '"2026-10-10T00:00:00Z"',
      },
      body: JSON.stringify({ display_name: 'Zee' }),
    });

    const env: ProxyEnv = {
      ORIGIN_URL: 'https://origin.internal:8000',
      CF_ACCESS_CLIENT_ID: 'access-id-123.access',
      CF_ACCESS_CLIENT_SECRET: 'access-secret-456',
    };

    const response = await handleProxy(request, env);
    expect(response.status).toBe(204);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [targetUrl, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(targetUrl).toBe('https://origin.internal:8000/api/v1/me');
    expect(init.method).toBe('PATCH');

    const sentHeaders = new Headers(init.headers);
    expect(sentHeaders.get('cf-access-client-id')).toBe('access-id-123.access');
    expect(sentHeaders.get('cf-access-client-secret')).toBe('access-secret-456');
    expect(sentHeaders.get('if-match')).toBe('"2026-10-10T00:00:00Z"');
  });

  it('returns 502 problem+json when upstream fetch throws network error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

    const request = new Request('https://app.example.com/api/v1/healthz');
    const env: ProxyEnv = {
      ORIGIN_URL: 'https://origin.internal:8000',
    };

    const response = await handleProxy(request, env);
    expect(response.status).toBe(502);
    expect(response.headers.get('content-type')).toBe('application/problem+json');
    const body = (await response.json()) as { title: string; status: number };
    expect(body.status).toBe(502);
    expect(body.title).toBe('Upstream service unavailable');
  });
});
