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

  constructor(status: number, title: string, detail: string, fieldErrors: FieldError[] = []) {
    super(`${String(status)} ${title}`);
    this.name = 'ApiError';
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
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

async function toApiError(response: Response): Promise<ApiError> {
  const type = response.headers.get('Content-Type') ?? '';
  if (type.includes('json')) {
    let body: ProblemBody;
    try {
      body = (await response.json()) as ProblemBody;
    } catch {
      // A proxy or gateway can label a non-JSON error page as JSON.
      return new ApiError(response.status, response.statusText, '');
    }
    const errors = Array.isArray(body.errors) ? body.errors.filter(isFieldError) : [];
    return new ApiError(
      response.status,
      typeof body.title === 'string' ? body.title : response.statusText,
      typeof body.detail === 'string' ? body.detail : '',
      errors,
    );
  }
  return new ApiError(response.status, response.statusText, '');
}

function timezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

export async function apiRequest<P extends ApiPath, M extends Method>(
  method: M,
  path: P,
  body?: RequestBody<Operation<P, M>>,
): Promise<SuccessBody<Operation<P, M>>> {
  const headers = new Headers({
    Accept: 'application/json, application/problem+json',
    // CSRF defence (spec 9.1): every request carries the client header; the browser adds Origin.
    'X-LifeOS-Client': 'web',
    // Spec 11.7: lets the server warn when device and profile timezones differ.
    'X-Timezone': timezone(),
  });
  const init: RequestInit = { method, headers, credentials: 'same-origin' };
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as SuccessBody<Operation<P, M>>;
  return (await response.json()) as SuccessBody<Operation<P, M>>;
}
