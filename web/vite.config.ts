import react from '@vitejs/plugin-react';
import { type ManifestOptions, VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vitest/config';

import pkg from './package.json' with { type: 'json' };
import { manifest } from './pwa.manifest.ts';

// `/api` goes to the local API, as the Pages Function forwards it in production (ADR-0001). The
// e2e stack sets LIFEOS_API to its own port (tests/journeys/stack.ts).
const apiProxy = { '/api': process.env['LIFEOS_API'] ?? 'http://127.0.0.1:8000' };

export default defineConfig({
  plugins: [
    react(),
    // Spec 11.3: our own service worker (src/sw.ts), the 11.2 manifest, updates on her say-so.
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'prompt',
      injectRegister: false,
      // Exactly spec 11.2: the plugin would otherwise add `lang: "en"`. An explicit undefined
      // overrides its default and is dropped when the manifest is written as JSON.
      manifest: { ...manifest, lang: undefined } as unknown as Partial<ManifestOptions>,
      injectManifest: {
        // The app shell, route chunks, fonts and icons (11.3); Ladle and test output never ship.
        globPatterns: ['**/*.{js,css,html,woff2,png,webmanifest}'],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: { host: true, proxy: apiProxy },
  preview: { host: true, proxy: apiProxy },
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}', 'tests/**/*.test.ts'],
    passWithNoTests: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.stories.tsx',
        'src/ui/tokens.ts',
        'src/lib/api/schema.d.ts',
        'src/vite-env.d.ts',
        'src/main.tsx',
        // Test helpers, not product code.
        'src/lib/testing/**',
      ],
      // Plan 4.7: web >= 80% lines for lib/.
      thresholds: { 'src/lib/**': { lines: 80 } },
    },
  },
});
