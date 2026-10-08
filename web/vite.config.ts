import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

import pkg from './package.json' with { type: 'json' };

// `/api` goes to the local API, as the Pages Function forwards it in production (ADR-0001). The
// e2e stack sets LIFEOS_API to its own port (tests/journeys/stack.ts).
const apiProxy = { '/api': process.env['LIFEOS_API'] ?? 'http://127.0.0.1:8000' };

export default defineConfig({
  plugins: [react()],
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
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
