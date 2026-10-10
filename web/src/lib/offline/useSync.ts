import { useEffect, useState } from 'react';

import { flushOutbox, getSyncState, subscribeSyncState } from './sync';
import type { SyncState } from './types';

export function useSync(): SyncState & { syncNow: () => Promise<void> } {
  const [state, setState] = useState<SyncState>(getSyncState);

  useEffect(() => {
    return subscribeSyncState((nextState) => {
      setState(nextState);
    });
  }, []);

  return {
    ...state,
    syncNow: flushOutbox,
  };
}
