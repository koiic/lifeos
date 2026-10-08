import { type QueryClient, useQuery } from '@tanstack/react-query';

import { api, ApiError } from '../api';
import { useLockStore } from '../lock/store';

/**
 * The server's `detail` for the auth refusals the client must tell apart (server/app/auth/
 * service.py; several share a status code). The journeys run against the real server, so a
 * changed message fails there.
 */
export const REASON = {
  notSignedIn: 'Sign in to continue.',
  notActivated: 'Confirm your authenticator app to finish setting up.',
  reauthRequired: "Confirm it's you to continue.",
  wrongPin: 'Wrong PIN.',
  pinLockedOut: 'Too many wrong PINs. Sign in again.',
  noPin: 'No app-lock PIN is set.',
  lastSignInMethod: 'This is your last way to sign in.',
} as const;

export function hasReason(error: unknown, status: number, reason: string): boolean {
  return error instanceof ApiError && error.status === status && error.detail === reason;
}

export type SessionStatus = 'loading' | 'signed-in' | 'signed-out' | 'pending' | 'error';

/** The session list doubles as the "am I signed in" check until `GET /me` exists (T09). */
export const SESSION_KEY = ['session'] as const;

type Probe = 'signed-in' | 'signed-out' | 'pending';

async function probe(): Promise<Probe> {
  try {
    await api.request('GET', '/api/v1/auth/sessions');
    return 'signed-in';
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return 'signed-out';
    if (hasReason(error, 403, REASON.notActivated)) return 'pending';
    throw error;
  }
}

export function useSession(): { status: SessionStatus; retry: () => void } {
  const query = useQuery({ queryKey: SESSION_KEY, queryFn: probe, staleTime: 30_000 });
  const status: SessionStatus = query.isPending ? 'loading' : query.isError ? 'error' : query.data;
  return {
    status,
    retry: () => {
      void query.refetch();
    },
  };
}

/**
 * Forget everything local about her (spec 11.4: sign-out and remote session revocation clear the
 * cache): every cached query except the session check itself, and the app lock.
 */
export function clearLocal(queryClient: QueryClient): void {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== SESSION_KEY[0] });
  useLockStore.getState().reset();
}

/** A session has just started (sign-in, registration, recovery): re-check it, and start unlocked
 * (a lock left by an earlier session that ended while locked does not carry over). */
export function startSession(queryClient: QueryClient): void {
  queryClient.removeQueries({ queryKey: SESSION_KEY });
  useLockStore.getState().reset();
}

/**
 * End the session and forget everything local. Local data is cleared even when the server
 * cannot be reached.
 */
export async function signOut(queryClient: QueryClient): Promise<void> {
  try {
    await api.request('POST', '/api/v1/auth/signout');
  } catch {
    // Offline or already signed out: the cookie expires on its own; local data still goes.
  }
  clearLocal(queryClient);
  queryClient.removeQueries({ queryKey: SESSION_KEY });
}
