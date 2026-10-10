import { useState } from 'react';
import { Outlet } from 'react-router-dom';

import { copy } from '../copy/en-GB';
import { BottomNav } from '../ui/BottomNav';
import { EmptyState } from '../ui/EmptyState';
import { Sheet } from '../ui/Sheet';
import styles from './AppShell.module.css';

const t = copy.nav;

// Spec 5.1: Today, Health, + (quick add), Calendar, More. `/health` opens the hub at Cycle, and
// the tab stays current on every Health screen.
const TABS = [
  { to: '/today', label: t.today, icon: 'home' },
  { to: '/health', label: t.health, icon: 'droplet' },
  { to: '/calendar', label: t.calendar, icon: 'calendar' },
  { to: '/more', label: t.more, icon: 'more' },
] as const;

/**
 * The signed-in layout (spec 5.1): the screen, then the bottom bar, "always visible except in
 * sheets and the lock screen". "+" opens the quick-add sheet; its six actions come with TOD-6.
 */
export function AppShell() {
  const [adding, setAdding] = useState(false);
  return (
    <div className={styles.shell}>
      <div className={styles.content}>
        <Outlet />
      </div>
      {!adding && (
        <div className={styles.bar}>
          <BottomNav
            label={t.label}
            items={TABS}
            action={{ label: t.add, onPress: () => setAdding(true) }}
          />
        </div>
      )}
      <Sheet
        open={adding}
        title={copy.quickAdd.title}
        closeLabel={copy.quickAdd.close}
        onClose={() => setAdding(false)}
      >
        <EmptyState title={copy.quickAdd.empty} body={copy.quickAdd.emptyBody} icon="plus" />
      </Sheet>
    </div>
  );
}
