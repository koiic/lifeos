import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { copy } from '../copy/en-GB';
import { clearLocal, useSession } from '../lib/auth/session';
import { ErrorState } from '../ui/ErrorState';
import { Skeleton } from '../ui/Skeleton';
import { Stack } from '../ui/Stack';

/**
 * Signed-in screens (AUTH-5): signed out → sign-in (and back here after); a password account
 * not yet confirmed → its code step (CR-014). Nothing of the screen renders until the session
 * is known. A server problem is not a sign-out: it offers a retry.
 */
export function RequireSession({ children }: { children: ReactNode }) {
  const { status, retry } = useSession();
  const location = useLocation();
  const queryClient = useQueryClient();

  // Signed out here means the session ended elsewhere too (revoked, expired): forget her data.
  useEffect(() => {
    if (status === 'signed-out') clearLocal(queryClient);
  }, [status, queryClient]);

  if (status === 'signed-in') return <>{children}</>;
  if (status === 'signed-out') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/signin?next=${next}`} replace />;
  }
  if (status === 'pending') return <Navigate to="/register?step=confirm" replace />;
  return (
    <Stack as="main" inset="page">
      {status === 'loading' ? (
        <Skeleton label={copy.common.loading} shapes={['line', 'block', 'block']} />
      ) : (
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: retry }}
        />
      )}
    </Stack>
  );
}
