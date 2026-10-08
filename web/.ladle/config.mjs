/** Ladle (spec 5.5, plan 5.3): one preview page per component, in Sorbet and Night Garden. */
export default {
  stories: 'src/ui/**/*.stories.tsx',
  viteConfig: '.ladle/vite.config.ts',
  port: 61000,
  previewPort: 61001,
  addons: {
    theme: { enabled: true, defaultState: 'light' },
    width: { enabled: true, defaultState: 390, options: { phone: 390 } },
    a11y: { enabled: false },
    msw: { enabled: false },
  },
};
