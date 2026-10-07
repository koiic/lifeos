// Client error reports (spec 11.7): message, route pattern and app version only; no user data.
import { apiRequest } from './client';

const MAX_MESSAGE = 500;

const EMAIL = /[^\s@]+@[^\s@]+/g;
const UUID = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
const DATE = /\d{4}-\d{2}-\d{2}(T[0-9:.]+(Z|[+-]\d{2}:?\d{2})?)?/g;
const NUMBER = /\d+/g;

/**
 * Replace anything that could be user data with placeholders: everything between the outermost
 * pair of each quote character (JSON.parse snippets, validation issues), then emails, UUIDs,
 * dates and numbers. The server applies the same rules (server/app/platform/client_errors.py).
 */
export function cleanMessage(message: string): string {
  let out = message;
  for (const quote of ['"', "'", '`']) {
    const first = out.indexOf(quote);
    const last = out.lastIndexOf(quote);
    if (first !== last) out = `${out.slice(0, first)}<str>${out.slice(last + 1)}`;
  }
  return out
    .replace(EMAIL, '<email>')
    .replace(UUID, '<uuid>')
    .replace(DATE, '<date>')
    .replace(NUMBER, '<n>');
}

function describe(error: unknown): string {
  if (error instanceof Error) return `${error.name}: ${cleanMessage(error.message)}`;
  // Thrown non-Errors can be arbitrary objects; report the type only.
  return `Non-Error thrown: ${typeof error}`;
}

/** Report an error; never throws, so it is safe inside error boundaries. */
export async function reportClientError(error: unknown, route: string): Promise<void> {
  try {
    await apiRequest('POST', '/api/v1/client-errors', {
      message: describe(error).slice(0, MAX_MESSAGE),
      route,
      version: __APP_VERSION__,
    });
  } catch {
    // Reporting is best effort: offline, rate-limited or server errors are ignored.
  }
}
