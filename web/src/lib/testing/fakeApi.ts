// Test helper: a fake of the API behind `fetch`, routed by "METHOD /path". Each route answers
// with a reply, or a list of replies used in turn (the last one repeats). Unknown routes fail
// the test loudly. Only for tests; screens still call the real `lib/api` client.
import { vi } from 'vitest';

export interface Reply {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export type Route = Reply | Reply[] | ((body: unknown) => Reply);

export interface FakeApi {
  /** Request bodies sent to a route, in order. */
  bodies(route: string): unknown[];
  /** How many times a route was called. */
  count(route: string): number;
  /** Request headers sent to a route, in order. */
  headers(route: string): Headers[];
  /** Replace or add routes. */
  set(routes: Record<string, Route>): void;
}

/** An RFC 9457 problem reply, as the server sends (spec 9.1). */
export function problem(status: number, detail: string, headers: Record<string, string> = {}) {
  return {
    status,
    body: { type: 'about:blank', title: 'Error', status, detail },
    headers: { 'Content-Type': 'application/problem+json', ...headers },
  };
}

export function fakeApi(initial: Record<string, Route>): FakeApi {
  const routes = new Map(Object.entries(initial));
  const seen = new Map<string, unknown[]>();
  const used = new Map<string, number>();
  const sentHeaders = new Map<string, Headers[]>();

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const key = `${init?.method ?? 'GET'} ${url}`;
    const route = routes.get(key);
    if (route === undefined) throw new Error(`fakeApi: no route for ${key}`);
    const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    seen.set(key, [...(seen.get(key) ?? []), body]);
    sentHeaders.set(key, [...(sentHeaders.get(key) ?? []), new Headers(init?.headers)]);
    const n = used.get(key) ?? 0;
    used.set(key, n + 1);
    const reply =
      typeof route === 'function'
        ? route(body)
        : Array.isArray(route)
          ? (route[Math.min(n, route.length - 1)] ?? {})
          : route;
    const status = reply.status ?? (reply.body === undefined ? 204 : 200);
    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status,
      headers: { 'Content-Type': 'application/json', ...reply.headers },
    });
  });
  vi.stubGlobal('fetch', fetchMock);

  return {
    bodies: (route) => seen.get(route) ?? [],
    count: (route) => used.get(route) ?? 0,
    headers: (route) => sentHeaders.get(route) ?? [],
    set: (more) => {
      for (const [key, value] of Object.entries(more)) routes.set(key, value);
    },
  };
}
