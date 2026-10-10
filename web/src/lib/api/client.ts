// Typed fetch wrapper over the generated OpenAPI types (spec 9, 11.1). Features call the API only
// through `lib/api` (plan 4.3).
import type { paths } from './schema';

export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type ApiPath = keyof paths;

type Operation<P extends ApiPath, M extends Method> = paths[P][Lowercase<M>];
type JsonContent<R> = R extends { content: { 'application/json': infer B } } ? B : undefined;
type SuccessBody<O> = O extends { responses: infer Rs }
  ? 200 extends keyof Rs
    ? JsonContent<Rs[200]>
    : 201 extends keyof Rs
      ? JsonContent<Rs[201]>
      : undefined
  : never;
type RequestBody<O> = O extends { requestBody: { content: { 'application/json': infer B } } }
  ? B
  : undefined;

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

/** An error response from the API, parsed from RFC 9457 problem+json when present (spec 9.1). */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string;
  readonly fieldErrors: readonly FieldError[];
  /** Seconds from a `Retry-After` header (429 lockouts and rate limits, spec 4.1, 9.1). */
  readonly retryAfterS: number | undefined;
  /** The whole problem body, e.g. a 409's `current` resource (9.1); empty when there was none. */
  readonly body: Readonly<Record<string, unknown>>;

  constructor(
    status: number,
    title: string,
    detail: string,
    fieldErrors: FieldError[] = [],
    retryAfterS?: number,
    body: Record<string, unknown> = {},
  ) {
    super(`${String(status)} ${title}`);
    this.name = 'ApiError';
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.retryAfterS = retryAfterS;
    this.body = body;
  }
}

interface ProblemBody {
  title?: unknown;
  detail?: unknown;
  errors?: unknown;
}

function isFieldError(value: unknown): value is FieldError {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v['field'] === 'string' &&
    typeof v['code'] === 'string' &&
    typeof v['message'] === 'string'
  );
}

function retryAfter(response: Response): number | undefined {
  const value = response.headers.get('Retry-After');
  return value !== null && /^\d+$/.test(value) ? Number(value) : undefined;
}

async function toApiError(response: Response): Promise<ApiError> {
  const type = response.headers.get('Content-Type') ?? '';
  const wait = retryAfter(response);
  if (type.includes('json')) {
    let body: ProblemBody;
    try {
      body = (await response.json()) as ProblemBody;
    } catch {
      // A proxy or gateway can label a non-JSON error page as JSON.
      return new ApiError(response.status, response.statusText, '', [], wait);
    }
    const errors = Array.isArray(body.errors) ? body.errors.filter(isFieldError) : [];
    return new ApiError(
      response.status,
      typeof body.title === 'string' ? body.title : response.statusText,
      typeof body.detail === 'string' ? body.detail : '',
      errors,
      wait,
      typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {},
    );
  }
  return new ApiError(response.status, response.statusText, '', [], wait);
}

function timezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** `{name}` segments of a path template, filled and URL-encoded. */
function fillPath(path: string, params: Record<string, string>): string {
  return path.replace(/\{([^}]+)\}/g, (_, name: string) => {
    const value = params[name];
    // Empty, "." and ".." would become a different path once the URL is normalised.
    if (value === undefined || value === '' || value === '.' || value === '..') {
      throw new Error(`apiRequest: no usable value for path parameter ${name}`);
    }
    return encodeURIComponent(value);
  });
}

export async function apiRequest<P extends ApiPath, M extends Method>(
  method: M,
  path: P,
  body?: RequestBody<Operation<P, M>>,
  params: Record<string, string> = {},
  extraHeaders: Record<string, string> = {},
  query?: Record<string, string | number | boolean | null | undefined>,
): Promise<SuccessBody<Operation<P, M>>> {
  let url = fillPath(path, params);
  if (query) {
    const searchParams = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) {
        searchParams.set(k, String(v));
      }
    }
    const qs = searchParams.toString();
    if (qs) {
      url += (url.includes('?') ? '&' : '?') + qs;
    }
  }
  const headers = new Headers({
    Accept: 'application/json, application/problem+json',
    // CSRF defence (spec 9.1): every request carries the client header; the browser adds Origin.
    'X-LifeOS-Client': 'web',
    // Spec 11.7: lets the server warn when device and profile timezones differ.
    'X-Timezone': timezone(),
    ...extraHeaders,
  });
  const init: RequestInit = { method, headers, credentials: 'same-origin' };
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  if (!response.ok) throw await toApiError(response);
  // No content (204, or e.g. a 201 Created with an empty body): nothing to parse.
  const text = response.status === 204 ? '' : await response.text();
  if (text === '') return undefined as SuccessBody<Operation<P, M>>;
  return JSON.parse(text) as SuccessBody<Operation<P, M>>;
}
