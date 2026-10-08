import { useRegisterSW } from 'virtual:pwa-register/react';

import { copy } from '../copy/en-GB';
import { Toast } from '../ui/Toast';

/**
 * Spec 11.3: registers the service worker (`registerType: 'prompt'`). When a new version is
 * waiting: "New version ready — Refresh". Refresh activates it and reloads; dismissing keeps the
 * current version, and the new one activates on the next cold start.
 */
export function UpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  if (!needRefresh) return null;
  return (
    <Toast
      placement="floating"
      message={copy.update.ready}
      action={{ label: copy.update.refresh, onClick: () => void updateServiceWorker(true) }}
      dismissLabel={copy.common.dismiss}
      onDismiss={() => setNeedRefresh(false)}
    />
  );
}
