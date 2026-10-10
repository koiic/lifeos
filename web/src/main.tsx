import './ui/tokens.css';
import './ui/fonts.css';
import './ui/base.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
import { applyTheme } from './lib/theme/theme';
import { savedTheme } from './lib/theme/ThemeSync';

// Open in the theme this device last used for her (SET-2); ThemeSync applies /me's once loaded.
applyTheme(savedTheme());

const container = document.getElementById('root');
if (!container) throw new Error('index.html has no #root element');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
