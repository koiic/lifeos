import { Navigate, Outlet, type RouteObject } from 'react-router-dom';

import { ThemeSync } from '../lib/theme/ThemeSync';
import { AppLock } from './AppLock';
import { AppShell } from './AppShell';
import { PushRefresh } from './PushRefresh';
import { RouteErrorBoundary, type RouteHandle } from './ErrorBoundary';
import { RequireSession } from './RequireSession';

const handle = (pattern: string): RouteHandle => ({ pattern });

/** Signed-in screens: the session is checked first, then the app lock (AUTH-5, AUTH-6). */
function SignedIn() {
  return (
    <RequireSession>
      <AppLock>
        <PushRefresh />
        <ThemeSync />
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
            // Spec 5.1: the tabs and Settings sit in the shell with the bottom bar.
            element: <AppShell />,
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
                path: 'checkin',
                handle: handle('/checkin'),
                lazy: async () => {
                  const { CheckInScreen } = await import('../features/checkin/CheckInScreen');
                  return { Component: CheckInScreen };
                },
              },
              {
                path: 'health',
                handle: handle('/health'),
                element: <Navigate to="/health/cycle" replace />,
              },
              {
                path: 'health/cycle',
                handle: handle('/health/cycle'),
                lazy: async () => {
                  const { HealthScreen } = await import('../features/health/HealthScreen');
                  return { Component: HealthScreen };
                },
              },
              {
                path: 'health/calendar',
                handle: handle('/health/calendar'),
                lazy: async () => {
                  const { CycleCalendarScreen } =
                    await import('../features/health/CycleCalendarScreen');
                  return { Component: CycleCalendarScreen };
                },
              },
              {
                path: 'health/history',
                handle: handle('/health/history'),
                lazy: async () => {
                  const { CycleHistoryScreen } =
                    await import('../features/health/CycleHistoryScreen');
                  return { Component: CycleHistoryScreen };
                },
              },
              {
                path: 'calendar',
                handle: handle('/calendar'),
                lazy: async () => {
                  const { CalendarScreen } = await import('../features/calendar/CalendarScreen');
                  return { Component: CalendarScreen };
                },
              },
              {
                path: 'more',
                handle: handle('/more'),
                lazy: async () => {
                  const { MoreScreen } = await import('../features/more/MoreScreen');
                  return { Component: MoreScreen };
                },
              },
              {
                path: 'settings',
                handle: handle('/settings'),
                lazy: async () => {
                  const { SettingsScreen } = await import('../features/settings/SettingsScreen');
                  return { Component: SettingsScreen };
                },
              },
              {
                path: 'settings/profile',
                handle: handle('/settings/profile'),
                lazy: async () => {
                  const { ProfileScreen } = await import('../features/settings/ProfileScreen');
                  return { Component: ProfileScreen };
                },
              },
              {
                path: 'settings/theme',
                handle: handle('/settings/theme'),
                lazy: async () => {
                  const { ThemeScreen } = await import('../features/settings/ThemeScreen');
                  return { Component: ThemeScreen };
                },
              },
              {
                path: 'settings/mode',
                handle: handle('/settings/mode'),
                lazy: async () => {
                  const { HealthModeScreen } =
                    await import('../features/settings/HealthModeScreen');
                  return { Component: HealthModeScreen };
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
          {
            path: 'setup',
            handle: handle('/setup'),
            lazy: async () => {
              const { SetupWizardScreen } =
                await import('../features/onboarding/SetupWizardScreen');
              return { Component: SetupWizardScreen };
            },
          },
          {
            path: 'setup/notifications',
            handle: handle('/setup/notifications'),
            lazy: async () => {
              const { NotificationsScreen } =
                await import('../features/onboarding/NotificationsScreen');
              return { Component: NotificationsScreen };
            },
          },
          {
            path: 'setup/:step',
            handle: handle('/setup/:step'),
            lazy: async () => {
              const { SetupWizardScreen } =
                await import('../features/onboarding/SetupWizardScreen');
              return { Component: SetupWizardScreen };
            },
          },
        ],
      },
    ],
  },
];
