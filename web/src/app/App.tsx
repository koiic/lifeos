import { useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { initAutoSync, restoreQueryCache, setupQueryCachePersistence } from '../lib/offline';
import { createQueryClient } from './queryClient';
import { routes } from './router';
import { UpdatePrompt } from './UpdatePrompt';

const queryClient = createQueryClient();
export const router = createBrowserRouter(routes);

if (typeof window !== 'undefined') {
  void restoreQueryCache(queryClient);
  setupQueryCachePersistence(queryClient);
  (window as unknown as { lifeosRouter?: typeof router }).lifeosRouter = router;
}

export function App() {
  useEffect(() => {
    return initAutoSync();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <UpdatePrompt />
    </QueryClientProvider>
  );
}
