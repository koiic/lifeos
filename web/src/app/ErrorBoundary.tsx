import { useEffect } from 'react';
import { isRouteErrorResponse, useMatches, useRouteError } from 'react-router-dom';

import { copy } from '../copy/en-GB';
import { reportClientError } from '../lib/api';

/** Every route declares its pattern, so reports never contain ids or dates from the URL. */
export interface RouteHandle {
  pattern: string;
}

function isRouteHandle(handle: unknown): handle is RouteHandle {
  return (
    typeof handle === 'object' &&
    handle !== null &&
    typeof (handle as Record<string, unknown>)['pattern'] === 'string'
  );
}

/** The deepest matched route's declared pattern; '/' when none is declared. */
export function reportedRoute(handles: readonly unknown[]): string {
  for (let i = handles.length - 1; i >= 0; i -= 1) {
    const handle = handles[i];
    if (isRouteHandle(handle)) return handle.pattern;
  }
  return '/';
}

/**
 * Top-level error boundary (spec 11.7): "Something went wrong — Reload", no stack traces.
 * Follow-up (T11/first screen task): render with the spec 5.5 ErrorState and Button components.
 */
export function RouteErrorBoundary() {
  const error = useRouteError();
  const route = reportedRoute(useMatches().map((match) => match.handle));

  useEffect(() => {
    // Unknown routes and other router responses are not client errors.
    if (!isRouteErrorResponse(error)) void reportClientError(error, route);
  }, [error, route]);

  return (
    <main>
      <h1>{copy.errors.title}</h1>
      <button
        type="button"
        onClick={() => {
          window.location.reload();
        }}
      >
        {copy.errors.reload}
      </button>
    </main>
  );
}
