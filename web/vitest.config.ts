import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['src/**/*.test.{ts,tsx}', 'tests/**/*.test.ts'],
    // T01 done-when: empty suites pass. Web unit tests arrive with T10.
    passWithNoTests: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.stories.tsx',
        'src/ui/tokens.ts',
        'src/lib/api/schema.d.ts',
      ],
      // Plan 4.7: web >= 80% lines for lib/.
      thresholds: { 'src/lib/**': { lines: 80 } },
    },
  },
});
