import { Navigate, Outlet, type RouteObject } from 'react-router-dom';

import { AppLock } from './AppLock';
import { RouteErrorBoundary, type RouteHandle } from './ErrorBoundary';
import { RequireSession } from './RequireSession';

const handle = (pattern: string): RouteHandle => ({ pattern });

/** Signed-in screens: the session is checked first, then the app lock (AUTH-5, AUTH-6). */
function SignedIn() {
  return (
    <RequireSession>
      <AppLock>
        <Outlet />
      </AppLock>
    </RequireSession>
  );
}

/**
 * Routes are code-split with `lazy` (spec 11.7); deep links per spec 5.1 arrive with features.
 * Every route declares `handle.pattern` (its full path pattern) for client error reports.
 */
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Outlet />,
    errorElement: <RouteErrorBoundary />,
    handle: handle('/'),
    children: [
      { index: true, element: <Navigate to="/today" replace /> },
      // Signed-out screens (spec 5.2): register from an invite, sign in, recover (AUTH-8).
      {
        path: 'register',
        handle: handle('/register'),
        lazy: async () => {
          const { RegisterScreen } = await import('../features/auth/RegisterScreen');
          return { Component: RegisterScreen };
        },
      },
      {
        path: 'signin',
        handle: handle('/signin'),
        lazy: async () => {
          const { SignInScreen } = await import('../features/auth/SignInScreen');
          return { Component: SignInScreen };
        },
      },
      {
        path: 'recover',
        handle: handle('/recover'),
        lazy: async () => {
          const { RecoverScreen } = await import('../features/auth/RecoverScreen');
          return { Component: RecoverScreen };
        },
      },
      {
        // ONB-1, J1 step 3: no data on it, so it works before and after signing in.
        path: 'install',
        handle: handle('/install'),
        lazy: async () => {
          const { InstallScreen } = await import('../features/onboarding/InstallScreen');
          return { Component: InstallScreen };
        },
      },
      {
        element: <SignedIn />,
        handle: handle('/'),
        children: [
          {
            path: 'today',
            handle: handle('/today'),
            lazy: async () => {
              const { TodayScreen } = await import('../features/today/TodayScreen');
              return { Component: TodayScreen };
            },
          },
          {
            path: 'settings/security',
            handle: handle('/settings/security'),
            lazy: async () => {
              const { SecurityScreen } = await import('../features/settings/SecurityScreen');
              return { Component: SecurityScreen };
            },
          },
        ],
      },
    ],
  },
];
