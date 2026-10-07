import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { reportClientError } from './clientErrors';

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function sentBody(): unknown {
  const init = fetchMock.mock.calls[0]?.[1];
  return JSON.parse(String(init?.body));
}

describe('reportClientError', () => {
  it('posts message, route pattern and version to /api/v1/client-errors', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await reportClientError(new TypeError('x is undefined'), '/health/cycle');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/client-errors');
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(sentBody()).toEqual({
      message: 'TypeError: x is undefined',
      route: '/health/cycle',
      version: __APP_VERSION__,
    });
  });

  it('truncates long messages to 500 characters', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await reportClientError(new Error('a'.repeat(900)), '/today');
    const body = sentBody() as { message: string };
    expect(body.message).toHaveLength(500);
  });

  it('reports non-Error values by type only', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await reportClientError({ secret: 'note' }, '/today');
    expect(sentBody()).toMatchObject({ message: 'Non-Error thrown: object' });
  });

  it('never throws, even when the report fails', async () => {
    fetchMock.mockRejectedValue(new TypeError('offline'));
    await expect(reportClientError(new Error('boom'), '/today')).resolves.toBeUndefined();
  });
});

describe('reportClientError cleaning (spec 11.7: no user data)', () => {
  function reportedMessage(): string {
    return (sentBody() as { message: string }).message;
  }

  it('sends the CSRF header, timezone and JSON content type', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await reportClientError(new Error('boom'), '/today');
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get('X-LifeOS-Client')).toBe('web');
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(headers.get('X-Timezone')).toBeTruthy();
  });

  it('removes the input snippet from a real JSON.parse error', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    let error: unknown;
    try {
      JSON.parse('{"flow":"heavy"');
    } catch (e) {
      error = e;
    }
    await reportClientError(error, '/checkin');
    expect(reportedMessage()).toMatch(/^SyntaxError: /);
    expect(reportedMessage()).not.toContain('heavy');
    expect(reportedMessage()).not.toContain('flow');
  });

  it('removes values from validation issue JSON', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const issues = JSON.stringify([
      { code: 'invalid_enum_value', received: 'heavy', path: ['flow'] },
    ]);
    await reportClientError(new Error(issues), '/checkin');
    expect(reportedMessage()).not.toContain('heavy');
  });

  it('removes dates, emails, ids and numbers', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await reportClientError(
      new RangeError(
        'bad 2026-10-06T09:30:00Z for zee@example.com dose 0192f2a1-7c3e-7f00-8a00-000000000001 x 42',
      ),
      '/today',
    );
    const message = reportedMessage();
    for (const leaked of ['2026', 'zee@', '0192f2a1', '42']) expect(message).not.toContain(leaked);
    expect(message).toBe('RangeError: bad <date> for <email> dose <uuid> x <n>');
  });
});
