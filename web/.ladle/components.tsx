import '../src/ui/tokens.css';
import '../src/ui/fonts.css';
import '../src/ui/base.css';
import './preview.css';

import type { GlobalProvider } from '@ladle/react';
import { useLayoutEffect } from 'react';

/** Renders every story in the theme Ladle's theme switch (or `?theme=`) selects. */
export const Provider: GlobalProvider = ({
  children,
  globalState,
}: Parameters<GlobalProvider>[0]) => {
  const theme = globalState.theme === 'dark' ? 'dark' : 'light';
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  // A landmark, as on a real screen (axe "region"); overlays render into <body> via a portal.
  return <main data-story-root>{children}</main>;
};
