// stylelint (plan 5.2): colours, fonts, radii, spacing, shadows and timings only through tokens.
// Tested by server/tests/tooling/test_stylelint.py.
const TOKEN_ONLY = [
  '/color$/',
  'fill',
  'stroke',
  'font-family',
  '/radius$/',
  '/^margin/',
  '/^padding/',
  'gap',
  'row-gap',
  'column-gap',
  'box-shadow',
  '/^transition-(duration|delay|timing-function)$/',
  '/^animation-(duration|delay|timing-function)$/',
];

// calc() is allowed only when built from tokens and plain numbers, e.g. calc(-1 * var(--space-2)).
const TOKEN_CALC = '/^calc\\((\\s*(var\\(--[a-z0-9-]+\\)|-?\\d+(\\.\\d+)?|[-+*/()]))+\\s*\\)$/';

export default {
  extends: ['stylelint-config-standard'],
  plugins: ['stylelint-declaration-strict-value'],
  // tokens.css is the one place raw values live (plan 5.1).
  ignoreFiles: ['src/ui/tokens.css'],
  allowEmptyInput: true,
  rules: {
    'color-no-hex': true,
    'color-named': 'never',
    'function-disallowed-list': [
      'rgb',
      'rgba',
      'hsl',
      'hsla',
      'hwb',
      'lab',
      'lch',
      'oklab',
      'oklch',
      'color',
      'color-mix',
    ],
    'scale-unlimited/declaration-strict-value': [
      TOKEN_ONLY,
      {
        ignoreFunctions: false,
        ignoreValues: [
          '0',
          '0s',
          'auto',
          'none',
          'inherit',
          'initial',
          'unset',
          'currentcolor',
          'transparent',
          TOKEN_CALC,
        ],
      },
    ],
    // A var() fallback would smuggle a raw value past the token rule.
    'declaration-property-value-disallowed-list': { '/.*/': ['/var\\(\\s*--[^,)]+,/'] },
    // Shorthands mix tokens with raw durations and font values; use the longhands.
    'property-disallowed-list': ['transition', 'animation', 'font'],
    // Decision (T01): CSS Modules class names are camelCase so they read as styles.cardTitle in TSX.
    'selector-class-pattern': '^[a-z][a-zA-Z0-9]*$',
  },
};
