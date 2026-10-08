import type { ReactNode } from 'react';

import styles from './Card.module.css';

export interface CardProps {
  as?: 'div' | 'section' | 'article';
  /** Id of the heading that names a section card. */
  labelledBy?: string;
  tone?: 'surface' | 'accent' | 'fertile' | 'sun' | 'lilac' | 'butter';
  /** Sticker Book accent: outline and offset shadow (spec 5.3). */
  sticker?: boolean;
  children: ReactNode;
}

/** A content card; tones are the theme's pastels (spec 5.3). */
export function Card({
  as: Element = 'div',
  labelledBy,
  tone = 'surface',
  sticker = false,
  children,
}: CardProps) {
  return (
    <Element
      className={styles.card}
      data-tone={tone}
      data-sticker={sticker}
      aria-labelledby={labelledBy}
    >
      {children}
    </Element>
  );
}
