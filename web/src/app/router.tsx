import { Navigate, Outlet, type RouteObject } from 'react-router-dom';

import { RouteErrorBoundary, type RouteHandle } from './ErrorBoundary';

const handle = (pattern: string): RouteHandle => ({ pattern });

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
      {
        path: 'today',
        handle: handle('/today'),
        lazy: async () => {
          const { TodayScreen } = await import('../features/today/TodayScreen');
          return { Component: TodayScreen };
        },
      },
    ],
  },
];
