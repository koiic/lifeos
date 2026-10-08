import type { ReactNode } from 'react';

import styles from './Stack.module.css';

export type Space = 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10;

export interface StackProps {
  as?: 'div' | 'section' | 'ul' | 'ol' | 'header' | 'footer' | 'form';
  direction?: 'column' | 'row';
  gap?: Space;
  align?: 'start' | 'center' | 'end' | 'stretch';
  justify?: 'start' | 'center' | 'end' | 'between';
  wrap?: boolean;
  children: ReactNode;
}

/** Layout primitive: children in a column or row with a spacing-token gap (plan 5.2). */
export function Stack({
  as: Element = 'div',
  direction = 'column',
  gap = 4,
  align = 'stretch',
  justify = 'start',
  wrap = false,
  children,
}: StackProps) {
  return (
    <Element
      className={styles.stack}
      data-direction={direction}
      data-gap={gap}
      data-align={align}
      data-justify={justify}
      data-wrap={wrap}
    >
      {children}
    </Element>
  );
}
