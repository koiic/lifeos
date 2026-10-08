import './ui/tokens.css';
import './ui/fonts.css';
import './ui/base.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
import { applyTheme } from './lib/theme/theme';

// Follow the device until the theme setting exists (SET-2, T17).
applyTheme('system');

const container = document.getElementById('root');
if (!container) throw new Error('index.html has no #root element');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
