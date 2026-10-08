// ESLint (plan 4.3, 5.2): typescript-eslint strict, react, react-hooks, jsx-a11y, Prettier, plus the
// web boundaries. Tested by server/tests/tooling/test_eslint.py.
import { readdirSync } from 'node:fs';

import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const STYLE = "JSXAttribute[name.name='style'] > JSXExpressionContainer";
const CUSTOM_PROPERTIES_ONLY = 'Inline style may only set CSS custom properties (plan 5.2).';

// Plan 5.2: no inline `style` except an object literal of CSS custom properties
// (style={{ '--progress': p }}), possibly chosen by a ternary.
const INLINE_STYLE = [
  ...[`${STYLE} > ObjectExpression`, `${STYLE} > ConditionalExpression > ObjectExpression`].flatMap(
    (object) => [
      { selector: `${object} > Property:not([key.value=/^--/])`, message: CUSTOM_PROPERTIES_ONLY },
      { selector: `${object} > SpreadElement`, message: CUSTOM_PROPERTIES_ONLY },
    ],
  ),
  {
    selector: `${STYLE} > :not(ObjectExpression, ConditionalExpression)`,
    message: CUSTOM_PROPERTIES_ONLY,
  },
  {
    selector: `${STYLE} > ConditionalExpression[consequent.type!='ObjectExpression']`,
    message: CUSTOM_PROPERTIES_ONLY,
  },
  {
    selector: `${STYLE} > ConditionalExpression[alternate.type!='ObjectExpression']`,
    message: CUSTOM_PROPERTIES_ONLY,
  },
];

// Plan 4.3: all user-facing text comes from src/copy/en-GB.ts. react/jsx-no-literals covers text
// children; these cover user-facing attributes and strings chosen inside JSX expressions.
const COPY_ONLY = 'User-facing text comes from src/copy/en-GB.ts (plan 4.3).';
const TEXT_ATTRIBUTE =
  'JSXAttribute[name.name=/^(aria-label|aria-description|aria-valuetext|aria-placeholder|aria-roledescription|title|alt|placeholder|label)$/]';
const STRING = 'Literal[raw=/^["\']/]';
const CHILD_EXPRESSION = ':matches(JSXElement, JSXFragment) > JSXExpressionContainer';
const USER_TEXT = [
  `${TEXT_ATTRIBUTE} > ${STRING}`,
  `${TEXT_ATTRIBUTE} > JSXExpressionContainer ${STRING}`,
  `${TEXT_ATTRIBUTE} > JSXExpressionContainer TemplateLiteral`,
  `${CHILD_EXPRESSION} :matches(ConditionalExpression, LogicalExpression) > ${STRING}`,
  `${CHILD_EXPRESSION} :matches(ConditionalExpression, LogicalExpression) > TemplateLiteral`,
].map((selector) => ({ selector, message: COPY_ONLY }));

const NOT_FEATURES = 'Features never import other features (plan 4.3).';

// Import rules every feature file follows (plan 4.3, 5.3).
const FEATURE_IMPORTS = [
  { regex: '(^|/)features/', message: NOT_FEATURES },
  { regex: '(^|/)app/', message: 'Features use src/ui and lib, not src/app internals (plan 4.3).' },
  { regex: '(^|/)lib/api/.+', message: 'Import the API only from lib/api (plan 4.3).' },
  {
    regex: '(^|/)ui/[^/]+/.+',
    message: 'Import UI components only from their src/ui/<Name> entry (plan 5.3).',
  },
];

// Relative imports that climb exactly to src/features/ and enter another feature. One block per
// feature folder and nesting depth, so parent imports inside the same feature stay allowed.
const MAX_DEPTH = 6;
const featureNames = readdirSync(new URL('./src/features/', import.meta.url), {
  withFileTypes: true,
})
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);
const perFeatureBoundaries = featureNames.flatMap((feature) =>
  Array.from({ length: MAX_DEPTH }, (_, depth) => ({
    files: [`src/features/${feature}/${'*/'.repeat(depth)}*.{ts,tsx}`],
    ignores: ['src/features/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: `^(\\.\\./){${String(depth + 1)}}(?!${feature}/)[^./]`,
              message: NOT_FEATURES,
            },
            ...FEATURE_IMPORTS,
          ],
        },
      ],
    },
  })),
);

const NO_NETWORK = 'Call the API through lib/api (plan 4.3).';
const NO_DATE = 'Use the helpers in lib/dates.ts for dates (plan 4.3).';

export default tseslint.config(
  {
    ignores: [
      'node_modules/',
      'coverage/',
      'dist/',
      'build/',
      'test-results/',
      'playwright-report/',
      '.lighthouseci/',
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
    files: ['src/**/*.{ts,tsx}'],
    rules: { 'no-restricted-syntax': ['error', ...INLINE_STYLE] },
  },
  {
    // Feature folders own their screens; they never reach into each other, API internals or the
    // network directly, and all their text comes from src/copy (plan 4.3).
    files: ['src/features/**/*.{ts,tsx}'],
    ignores: ['src/features/**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', { patterns: FEATURE_IMPORTS }],
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: NO_NETWORK },
        { name: 'XMLHttpRequest', message: NO_NETWORK },
        { name: 'Date', message: NO_DATE },
      ],
      'no-restricted-properties': [
        'error',
        ...['window', 'globalThis', 'self'].flatMap((object) => [
          { object, property: 'fetch', message: NO_NETWORK },
          { object, property: 'XMLHttpRequest', message: NO_NETWORK },
          { object, property: 'Date', message: NO_DATE },
        ]),
      ],
      'no-restricted-syntax': ['error', ...INLINE_STYLE, ...USER_TEXT],
      'react/jsx-no-literals': ['error', { noStrings: true, ignoreProps: true }],
    },
  },
  ...perFeatureBoundaries,
  {
    files: ['*.config.js', '*.config.ts'],
    languageOptions: { globals: { ...globals.node } },
  },
  prettier,
);
