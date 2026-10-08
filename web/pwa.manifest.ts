// Spec 11.2: the web app manifest. Its colours are the Sorbet page background token (`--bg`),
// read from the design tokens (plan 5.1: no colour written anywhere else).
import type { ManifestOptions } from 'vite-plugin-pwa';

import tokens from '../design/tokens.json' with { type: 'json' };

const background = tokens.themes.light.color.bg;

export const manifest: Partial<ManifestOptions> = {
  name: 'Life OS',
  short_name: 'Life OS',
  id: '/',
  start_url: '/today?source=pwa',
  scope: '/',
  display: 'standalone',
  orientation: 'portrait',
  background_color: background,
  theme_color: background,
  icons: [
    { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    {
      src: '/icons/icon-maskable-512.png',
      sizes: '512x512',
      type: 'image/png',
      purpose: 'maskable',
    },
  ],
};
