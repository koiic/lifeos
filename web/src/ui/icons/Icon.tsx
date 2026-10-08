import type { ReactElement } from 'react';

import styles from './Icon.module.css';

/** Plan 5.2: icons on a 24 px grid, 2 px stroke, currentColor; drawn for Life OS. */
const ICONS = {
  close: [<path key="a" d="M6 6l12 12M18 6L6 18" />],
  check: [<path key="a" d="M5 12.5l4.5 4.5L19 7.5" />],
  plus: [<path key="a" d="M12 5v14M5 12h14" />],
  chevronDown: [<path key="a" d="M6 9l6 6 6-6" />],
  chevronLeft: [<path key="a" d="M15 6l-6 6 6 6" />],
  chevronRight: [<path key="a" d="M9 6l6 6-6 6" />],
  alert: [<circle key="a" cx="12" cy="12" r="9" />, <path key="b" d="M12 7.5v5.5M12 16.5v.5" />],
  info: [<circle key="a" cx="12" cy="12" r="9" />, <path key="b" d="M12 11v5.5M12 7.5v.5" />],
  home: [<path key="a" d="M4 10.5L12 4l8 6.5V20h-5v-6h-6v6H4z" />],
  calendar: [
    <rect key="a" x="3" y="5" width="18" height="16" rx="2" />,
    <path key="b" d="M3 10h18M8 3v4M16 3v4" />,
  ],
  droplet: [<path key="a" d="M12 3.5c3 4 6 7.2 6 10.5a6 6 0 0 1-12 0c0-3.3 3-6.5 6-10.5z" />],
  settings: [
    <path key="a" d="M4 7h10M18 7h2M4 17h4M12 17h8" />,
    <circle key="b" cx="16" cy="7" r="2" />,
    <circle key="c" cx="10" cy="17" r="2" />,
  ],
  clock: [<circle key="a" cx="12" cy="12" r="9" />, <path key="b" d="M12 7v5l3 2" />],
  trash: [<path key="a" d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />],
  edit: [<path key="a" d="M4 20h4L19 9l-4-4L4 16z" />],
  more: [<path key="a" d="M6 12h.01M12 12h.01M18 12h.01" />],
} satisfies Record<string, ReactElement[]>;

export type IconName = keyof typeof ICONS;
export const iconNames = Object.keys(ICONS) as IconName[];

export interface IconProps {
  name: IconName;
  size?: 'md' | 'sm';
}

/** Decorative: the control that holds an icon carries the accessible name (spec 5.8). */
export function Icon({ name, size = 'md' }: IconProps) {
  return (
    <svg
      className={styles.icon}
      data-size={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {ICONS[name]}
    </svg>
  );
}
