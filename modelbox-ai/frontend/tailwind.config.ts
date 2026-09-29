import type { Config } from 'tailwindcss';

import { color, entityAccent, fontFamily, semantic } from './src/styles/tokens';

/**
 * The theme is *derived* from `src/styles/tokens.ts`, never restated here.
 *
 * The entity accents used to be declared independently in both files — six hex
 * values maintained in two places, which is the arrangement that guarantees one
 * of them is eventually wrong. `test_tailwind_theme_is_derived_from_the_token_module`
 * asserts the identity, so the duplication cannot come back by hand.
 */
const config: Config = {
  content: ['./src/app/**/*.{ts,tsx}', './src/components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        entity: entityAccent,
        brand: {
          navy: color.navy,
          blue: color.blue,
          cyan: color.cyan,
        },
        neutral: color.neutral,
        validated: semantic.validated,
        breaking: semantic.breaking,
        preview: semantic.preview,
      },
      fontFamily: {
        sans: [fontFamily.sans],
        mono: [fontFamily.mono],
      },
    },
  },
  plugins: [],
};

export default config;
