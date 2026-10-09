import { useEffect } from 'react';

import { refreshSubscription } from '../lib/push/push';

/**
 * Spec 10.5: on every start of the signed-in app, this device's push subscription is saved
 * again (or renewed if the browser dropped it). Never asks for permission; failures are quiet.
 */
export function PushRefresh() {
  useEffect(() => {
    refreshSubscription().catch(() => undefined);
  }, []);
  return null;
}
