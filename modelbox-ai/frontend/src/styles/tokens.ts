/**
 * Design tokens — the machine-readable twin of `docs/ModelBox_AI_Design_Tokens.md`.
 *
 * That document is the specification; this file is what the code imports, and
 * `tokens.spec.test.ts` fails if the two disagree. Neither is allowed to be the
 * only place a value exists.
 *
 * **Why a foreground is never exported on its own.** Every semantic role has an
 * on-light and an on-dark variant, and picking the wrong one is not a style
 * mistake — it is an unreadable status message. The brand's Emerald measures
 * 2.54:1 on white and Amber 2.15:1, so on the light surfaces that make up all
 * of this product except the canvas, both are invisible as text. The API below
 * therefore reaches a colour through the surface it sits on (`onLight`,
 * `onDark`), which makes the unreadable combination unavailable rather than
 * merely discouraged.
 */

export const color = {
  navy: '#0A1628',
  blue: '#2563EB',
  cyan: '#06B6D4',
  white: '#FFFFFF',
  neutral: {
    50: '#F8FAFC',
    100: '#F1F5F9',
    200: '#E2E8F0',
    300: '#CBD5E1',
    400: '#94A3B8',
    500: '#64748B',
    600: '#475569',
    700: '#334155',
    800: '#1E293B',
    900: '#0F172A',
  },
} as const;

/** The grounds a foreground can sit on. Named, because the pair is the unit. */
export const surface = {
  page: color.neutral[50],
  card: color.white,
  dark: color.navy,
} as const;

/**
 * Status colour by role and by ground.
 *
 * `onDark` values are the brand's original Emerald / Rose / Amber — correct for
 * the ground they were chosen against. `onLight` values are their 700-weight
 * equivalents, each the lightest value in its hue clearing 4.5:1 on both light
 * surfaces. `#E11D48` was rejected for `breaking.onLight` at 4.49:1.
 */
export const semantic = {
  validated: { onLight: '#047857', onDark: '#10B981' },
  breaking: { onLight: '#BE123C', onDark: '#F43F5E' },
  preview: { onLight: '#B45309', onDark: '#F59E0B' },
} as const;

/**
 * Canvas node accents, by entity type.
 *
 * Defined once. `tailwind.config.ts` imports this rather than restating it —
 * the two previously held the same six values independently, which is the
 * duplication that makes one of them wrong eventually.
 */
export const entityAccent = {
  TABLE: '#64748B',
  FACT: '#2563EB',
  DIMENSION: '#16A34A',
  HUB: '#9333EA',
  LINK: '#EA580C',
  SATELLITE: '#0891B2',
} as const;

export const type = {
  display: { size: '3.5rem', weight: 800, lineHeight: 1.05, tracking: '-0.03em' },
  h1: { size: '2.25rem', weight: 800, lineHeight: 1.1, tracking: '-0.025em' },
  h2: { size: '1.5rem', weight: 700, lineHeight: 1.2, tracking: '-0.02em' },
  h3: { size: '1.125rem', weight: 700, lineHeight: 1.3, tracking: '-0.01em' },
  body: { size: '1rem', weight: 400, lineHeight: 1.6, tracking: '0' },
  bodySmall: { size: '0.875rem', weight: 400, lineHeight: 1.5, tracking: '0.005em' },
  caption: { size: '0.75rem', weight: 500, lineHeight: 1.4, tracking: '0.02em' },
  code: { size: '0.8125rem', weight: 400, lineHeight: 1.6, tracking: '0' },
  // The UI-density pair. The content ramp above bottoms out at 0.75rem, but
  // 78% of the frontend's 158 font sizes are 13/12/11px — dense controls,
  // labels and badges, which are a different scale from prose rather than
  // small prose. Mapping them onto the content ramp would move type on more
  // than a hundred elements; naming them moves nothing. `uiSmall` shares a
  // size with `code` and not its role: `code` is the monospace face.
  uiSmall: { size: '0.8125rem', weight: 400, lineHeight: 1.45, tracking: '0' },
  uiXSmall: { size: '0.6875rem', weight: 600, lineHeight: 1.3, tracking: '0.02em' },
} as const;

export const fontFamily = {
  sans: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
} as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

/**
 * `xl` is the modal corner. It is not a rounding of an existing step — the
 * frontend uses 3, 10, 12 and 14 today, and of those only 12 recurs as a
 * deliberate shape rather than as a near-miss of one already named here.
 */
export const radius = { sm: 4, md: 6, lg: 8, xl: 12, pill: 999 } as const;

/**
 * The focus ring. There are zero focus declarations in the frontend today, so
 * keyboard users navigate on the user-agent default or on nothing at all.
 */
export const focusRing = {
  outline: `2px solid ${color.blue}`,
  outlineOffset: '2px',
} as const;

export type ContrastRole = 'body' | 'large';

export interface ContrastPair {
  readonly name: string;
  readonly fg: string;
  readonly bg: string;
  readonly role: ContrastRole;
}

/**
 * Every foreground/background combination the product actually uses.
 *
 * Iterated by `test_every_declared_pair_meets_its_contrast_floor`, never listed
 * there — a gate is only as broad as the fixtures it is parameterised over, and
 * a hand-kept list in the test would drift from the one here. Adding a pair
 * here is what puts it under the floor check.
 *
 * `role: 'large'` is the 3:1 floor: text at 24px or 18.66px bold, and non-text
 * boundaries such as the canvas node accents, which sit behind white rather
 * than being read themselves.
 */
export const PAIRS: readonly ContrastPair[] = [
  { name: 'body on page', fg: color.neutral[600], bg: surface.page, role: 'body' },
  { name: 'body on card', fg: color.neutral[600], bg: surface.card, role: 'body' },
  { name: 'heading on page', fg: color.neutral[900], bg: surface.page, role: 'body' },
  { name: 'secondary on page', fg: color.neutral[500], bg: surface.page, role: 'body' },
  { name: 'link on page', fg: color.blue, bg: surface.page, role: 'body' },
  { name: 'link on card', fg: color.blue, bg: surface.card, role: 'body' },
  { name: 'white on dark', fg: color.white, bg: surface.dark, role: 'body' },
  { name: 'cyan on dark', fg: color.cyan, bg: surface.dark, role: 'body' },

  { name: 'validated on page', fg: semantic.validated.onLight, bg: surface.page, role: 'body' },
  { name: 'validated on card', fg: semantic.validated.onLight, bg: surface.card, role: 'body' },
  { name: 'validated on dark', fg: semantic.validated.onDark, bg: surface.dark, role: 'body' },
  { name: 'breaking on page', fg: semantic.breaking.onLight, bg: surface.page, role: 'body' },
  { name: 'breaking on card', fg: semantic.breaking.onLight, bg: surface.card, role: 'body' },
  { name: 'breaking on dark', fg: semantic.breaking.onDark, bg: surface.dark, role: 'body' },
  { name: 'preview on page', fg: semantic.preview.onLight, bg: surface.page, role: 'body' },
  { name: 'preview on card', fg: semantic.preview.onLight, bg: surface.card, role: 'body' },
  { name: 'preview on dark', fg: semantic.preview.onDark, bg: surface.dark, role: 'body' },

  // Node accents carry white text; held to the non-text / large floor.
  ...(Object.entries(entityAccent).map(([entity, accent]) => ({
    name: `white on ${entity.toLowerCase()} accent`,
    fg: color.white,
    bg: accent,
    role: 'large' as const,
  })) as readonly ContrastPair[]),
] as const;

export const CONTRAST_FLOOR: Readonly<Record<ContrastRole, number>> = {
  body: 4.5,
  large: 3,
};

/** WCAG 2.x relative luminance. */
export function relativeLuminance(hex: string): number {
  const h = hex.replace('#', '');
  const channel = (i: number): number => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

/** WCAG 2.x contrast ratio, 1..21. */
export function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
