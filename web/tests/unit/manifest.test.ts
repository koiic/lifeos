import { describe, expect, it } from 'vitest';

import tokens from '../../../design/tokens.json' with { type: 'json' };
import { manifest } from '../../pwa.manifest';

describe('[ONB-1] web app manifest (spec 11.2)', () => {
  it('is exactly the spec manifest, with its colours from the Sorbet tokens', () => {
    expect(manifest).toEqual({
      name: 'Life OS',
      short_name: 'Life OS',
      id: '/',
      start_url: '/today?source=pwa',
      scope: '/',
      display: 'standalone',
      orientation: 'portrait',
      background_color: '#FFF4F1',
      theme_color: '#FFF4F1',
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
    });
  });

  it('its colours are the Sorbet --bg token, not a copy of it', () => {
    expect(manifest.background_color).toBe(tokens.themes.light.color.bg);
    expect(manifest.theme_color).toBe(tokens.themes.light.color.bg);
  });
});
