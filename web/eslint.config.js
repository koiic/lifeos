// ESLint (plan 4.3): typescript-eslint strict, react, react-hooks, jsx-a11y, Prettier.
// Feature boundaries, copy and date rules are added with the web scaffold (T10).
import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'node_modules/',
      'coverage/',
      'dist/',
      // Generated files (plan 5.1, 4.4); their generators are checked instead.
      'src/ui/tokens.ts',
      'src/lib/api/schema.d.ts',
    ],
  },
  js.configs.recommended,
  tseslint.configs.strict,
  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'],
  reactHooks.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    languageOptions: { globals: { ...globals.browser } },
    settings: { react: { version: '18' } },
  },
  {
    files: ['*.config.js', '*.config.ts', 'tests/tooling/**'],
    languageOptions: { globals: { ...globals.node } },
  },
  prettier,
);
