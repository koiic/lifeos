import type { ReactNode } from 'react';

import type { Space } from '../Stack';
import styles from './Grid.module.css';

export interface GridProps {
  columns: 1 | 2 | 3 | 4;
  gap?: Space;
  children: ReactNode;
}

/** Layout primitive: equal columns with a spacing-token gap (plan 5.2). */
export function Grid({ columns, gap = 4, children }: GridProps) {
  return (
    <div className={styles.grid} data-columns={columns} data-gap={gap}>
      {children}
    </div>
  );
}
