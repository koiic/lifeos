import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiRequest } from './client';

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200, type = 'application/json'): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } });
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function sentInit(): RequestInit {
  const call = fetchMock.mock.calls[0];
  if (!call) throw new Error('fetch was not called');
  return call[1] ?? {};
}

describe('apiRequest', () => {
  it('sends the client header, timezone and same-origin credentials', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 'ok' }));
    await apiRequest('GET', '/api/v1/healthz');
    const init = sentInit();
    const headers = new Headers(init.headers);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/healthz');
    expect(init.method).toBe('GET');
    expect(init.credentials).toBe('same-origin');
    expect(headers.get('X-LifeOS-Client')).toBe('web');
    expect(headers.get('X-Timezone')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
    expect(headers.get('Accept')).toBe('application/json, application/problem+json');
  });

  it('returns the parsed JSON body', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 'ok' }));
    await expect(apiRequest('GET', '/api/v1/healthz')).resolves.toEqual({ status: 'ok' });
  });

  it('sends a JSON body on mutations', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const result = await apiRequest('POST', '/api/v1/client-errors', {
      message: 'm',
      route: '/today',
      version: '0.1.0',
    });
    const init = sentInit();
    expect(result).toBeUndefined();
    expect(init.body).toBe(JSON.stringify({ message: 'm', route: '/today', version: '0.1.0' }));
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json');
  });

  it('turns problem+json into an ApiError with field errors', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          type: 'about:blank',
          title: 'Unprocessable Content',
          status: 422,
          detail: 'The request has invalid fields.',
          errors: [{ field: 'route', code: 'string_pattern_mismatch', message: 'Bad route' }],
        },
        422,
        'application/problem+json',
      ),
    );
    const error = await apiRequest('GET', '/api/v1/healthz').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.title).toBe('Unprocessable Content');
    expect(apiError.detail).toBe('The request has invalid fields.');
    expect(apiError.fieldErrors).toEqual([
      { field: 'route', code: 'string_pattern_mismatch', message: 'Bad route' },
    ]);
  });

  it('handles an error response that is not problem+json', async () => {
    fetchMock.mockResolvedValue(new Response('Bad gateway', { status: 502 }));
    const error = await apiRequest('GET', '/api/v1/healthz').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).fieldErrors).toEqual([]);
  });
});

describe('apiRequest details', () => {
  it('sends the device timezone (not a hard-coded default)', async () => {
    const real = Intl.DateTimeFormat;
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(
      (...args: ConstructorParameters<typeof Intl.DateTimeFormat>) => {
        const format = new real(...args);
        vi.spyOn(format, 'resolvedOptions').mockReturnValue({
          ...format.resolvedOptions(),
          timeZone: 'America/New_York',
        });
        return format;
      },
    );
    fetchMock.mockResolvedValue(jsonResponse({ status: 'ok' }));
    await apiRequest('GET', '/api/v1/healthz');
    expect(new Headers(sentInit().headers).get('X-Timezone')).toBe('America/New_York');
    vi.restoreAllMocks();
  });

  it('sends the CSRF header on mutations too', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await apiRequest('POST', '/api/v1/client-errors', {
      message: 'm',
      route: '/today',
      version: '0.1.0',
    });
    expect(new Headers(sentInit().headers).get('X-LifeOS-Client')).toBe('web');
  });

  it('falls back to the status text when a problem has no title or detail', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 503 }), {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'application/problem+json' },
      }),
    );
    const error = (await apiRequest('GET', '/api/v1/readyz').catch((e: unknown) => e)) as ApiError;
    expect(error.title).toBe('Service Unavailable');
    expect(error.detail).toBe('');
  });

  it('still raises ApiError when a JSON error body is malformed', async () => {
    fetchMock.mockResolvedValue(
      new Response('<html>proxy error</html>', {
        status: 502,
        statusText: 'Bad Gateway',
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const error = await apiRequest('GET', '/api/v1/healthz').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).title).toBe('Bad Gateway');
  });

  it('[AUTH-7] keeps Retry-After (seconds) so a lockout can say how long to wait', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ title: 'Too Many Requests', detail: 'later' }), {
        status: 429,
        headers: { 'Content-Type': 'application/problem+json', 'Retry-After': '840' },
      }),
    );
    const error = await apiRequest('GET', '/api/v1/healthz').catch((e: unknown) => e);
    expect((error as ApiError).retryAfterS).toBe(840);
  });

  it('ignores a missing or unreadable Retry-After', async () => {
    fetchMock.mockResolvedValue(
      new Response('{}', {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Retry-After': 'soon' },
      }),
    );
    const error = await apiRequest('GET', '/api/v1/healthz').catch((e: unknown) => e);
    expect((error as ApiError).retryAfterS).toBeUndefined();
  });

  it('fills path parameters, encoded', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await apiRequest('DELETE', '/api/v1/auth/sessions/{session_id}', undefined, {
      session_id: 'a/b c',
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/sessions/a%2Fb%20c');
  });

  it('refuses a path with a parameter left unfilled', async () => {
    await expect(apiRequest('DELETE', '/api/v1/auth/sessions/{session_id}')).rejects.toThrow(
      'session_id',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['', '.', '..'])('refuses %j as a path parameter (no dot segments)', async (value) => {
    await expect(
      apiRequest('DELETE', '/api/v1/auth/sessions/{session_id}', undefined, { session_id: value }),
    ).rejects.toThrow('session_id');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('a success with an empty body (e.g. 201 Created) returns nothing, without failing', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 201 }));
    await expect(
      apiRequest('POST', '/api/v1/push/subscriptions', {
        endpoint: 'https://fcm.googleapis.com/x',
        keys: { p256dh: 'B', auth: 'a' },
      }),
    ).resolves.toBeUndefined();
  });
});

describe('versions and conflicts (spec 9.1, CR-004)', () => {
  it('sends extra headers such as If-Match', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ theme: 'dark' }));
    await apiRequest('PATCH', '/api/v1/me/settings', { theme: 'dark' }, {}, { 'If-Match': '"v1"' });
    expect(new Headers(sentInit().headers).get('If-Match')).toBe('"v1"');
  });

  it('keeps the problem body, so a 409 can hand over the current resource', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          type: 'about:blank',
          title: 'Conflict',
          status: 409,
          detail: 'Changed elsewhere.',
          current: { theme: 'light', version: 'v2' },
        },
        409,
        'application/problem+json',
      ),
    );
    const error = await apiRequest('PATCH', '/api/v1/me/settings', { theme: 'dark' }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).body['current']).toEqual({ theme: 'light', version: 'v2' });
  });

  it('an error without a JSON body has an empty problem body', async () => {
    fetchMock.mockResolvedValue(new Response('down', { status: 502, statusText: 'Bad Gateway' }));
    const error = (await apiRequest('GET', '/api/v1/healthz').catch((e: unknown) => e)) as ApiError;
    expect(error.body).toEqual({});
  });
});
