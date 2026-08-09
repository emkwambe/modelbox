import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/app/**/*.{ts,tsx}',
    './src/components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Entity-type accents shared with the canvas node renderer.
        entity: {
          table: '#64748b',
          fact: '#2563eb',
          dimension: '#16a34a',
          hub: '#9333ea',
          link: '#ea580c',
          satellite: '#0891b2',
        },
      },
    },
  },
  plugins: [],
};

export default config;
