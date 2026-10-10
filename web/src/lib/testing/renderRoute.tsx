// Test helper: render a screen at a URL inside a router and a fresh query client. The other
// routes the app has are stand-ins that print their path, so a test can see where it went.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router-dom';

const OTHER_ROUTES = [
  '/today',
  '/signin',
  '/register',
  '/settings/security',
  '/install',
  '/checkin',
];

function Arrived() {
  const location = useLocation();
  return <p data-testid="arrived">{`${location.pathname}${location.search}`}</p>;
}

export function renderRoute(element: ReactElement, { path, url }: { path: string; url: string }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path, element },
      ...OTHER_ROUTES.filter((other) => other !== path).map((other) => ({
        path: other,
        element: <Arrived />,
      })),
    ],
    { initialEntries: [url] },
  );
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, queryClient, router };
}
