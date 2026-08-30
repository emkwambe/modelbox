# ModelBox AI — design tokens

**Status: specification.** This is the authority for colour and type in the
product. `frontend/src/styles/tokens.ts` is its machine-readable twin, and
`tokens.spec.test.ts` fails if the two disagree.

It exists because criteria F1 and F6 previously cited
`docs/research/ModelBox_AI_Brand_Design_System.md`, and **criterion E5
quarantines `docs/research/` as "cannot be read as specification."** The
register pointed at a document the register forbids citing. That research
document keeps its quarantine and its history; this file is the specification
extracted from it, corrected.

---

## The correction that made this file necessary

The research document's contrast table was measured. **Three of its published
ratios are wrong, and one is wrong in the unsafe direction.**

| Pair | Document claimed | Measured | |
| :-- | :-- | :-- | :-- |
| Rose `#F43F5E` on white | 5.3:1 "AA" | **3.67:1** | **fails the document's own 4.5:1 body floor** |
| Emerald `#10B981` on Neutral-900 | 6.4:1 | 7.04:1 | understated |
| Cyan `#06B6D4` on Navy | 7.8:1 | 7.47:1 | overstated, still passes |
| Blue `#2563EB` on white | 4.8:1 | 5.17:1 | understated |

The deeper problem is what the table never contained. **Every application
surface except the canvas is light** — `--background: #f8fafc` — and the
research document tabulated its semantic colours only against dark grounds:

| Never tabulated | Measured on white | |
| :-- | :-- | :-- |
| Emerald `#10B981` | **2.54:1** | unusable as body text |
| Amber `#F59E0B` | **2.15:1** | unusable as body text |

**The brand palette was specified for a dark visual identity. The product is
light.** That is not a transcription error to fix by copying more carefully; it
is a gap that had to be closed by choosing values the research document does not
contain.

Two of those hues were already shipping wrongly: `#16a34a` (success, used 11
times) measures **3.30:1** on white and fails today.

---

## Semantic roles

Each role has an **on-light** and an **on-dark** variant. They are not
interchangeable, and the token API requires the surface to be named so the wrong
one cannot be reached by accident.

| Role | On light (`#F8FAFC` / `#FFFFFF`) | On dark (`#0A1628`) | Meaning |
| :-- | :-- | :-- | :-- |
| **validated** | `#047857` | `#10B981` | Passed, valid, certified |
| **breaking** | `#BE123C` | `#F43F5E` | Failed, breaking change, error |
| **preview** | `#B45309` | `#F59E0B` | Preview, warning, not deployment-verified |

The on-dark variants are the research document's original Emerald, Rose and
Amber — they were right for the ground they were chosen against. The on-light
variants are the 700-weight equivalents, selected as the lightest value in each
hue that clears 4.5:1 on both light surfaces.

`#E11D48` was rejected for breaking-on-light at **4.49:1** — under the floor by
0.01. Recording the near-miss because it is the value a designer would reach for
first, and because "close enough" is how a contrast floor stops meaning anything.

---

## Palette

| Token | Value | Use |
| :-- | :-- | :-- |
| `navy` | `#0A1628` | Dark ground, canvas node headers |
| `blue` | `#2563EB` | Primary action, links |
| `cyan` | `#06B6D4` | Accent on dark only — 1.79:1 on white |
| `neutral.50` | `#F8FAFC` | Page ground |
| `neutral.100` | `#F1F5F9` | Subtle fill |
| `neutral.200` | `#E2E8F0` | Borders, dividers |
| `neutral.300` | `#CBD5E1` | Disabled, placeholder — **1.48:1 on white, never text** |
| `neutral.400` | `#94A3B8` | Non-essential metadata only — 2.35:1, fails as body |
| `neutral.500` | `#64748B` | Secondary text — 4.55:1, at the floor |
| `neutral.600` | `#475569` | Body text |
| `neutral.700` | `#334155` | Headings |
| `neutral.800` | `#1E293B` | Strong headings |
| `neutral.900` | `#0F172A` | Primary text |
| `white` | `#FFFFFF` | Card ground |

Two of these carry warnings rather than uses. `neutral.300` and `neutral.400`
appear 25 and 18 times in the current code, and neither can legally carry body
text. The token names say so; the contrast test enforces it for any pair
actually declared.

## Entity accents

Canvas node headers, on dark. Previously duplicated between
`tailwind.config.ts` and `EntityNode.tsx` — now defined once.

| Entity type | Value |
| :-- | :-- |
| `TABLE` | `#64748B` |
| `FACT` | `#2563EB` |
| `DIMENSION` | `#16A34A` |
| `HUB` | `#9333EA` |
| `LINK` | `#EA580C` |
| `SATELLITE` | `#0891B2` |

These are accents behind white text, not text themselves, so they are held to
the 3:1 large/non-text floor rather than 4.5:1.

---

## Type

Inter for UI, JetBrains Mono for code and data. **Self-hosted**, not fetched at
build time: the appliance is air-gapped and a `docker build` without network
must not fail.

| Token | Size | Weight | Line height | Tracking |
| :-- | :-- | :-- | :-- | :-- |
| `display` | 3.5rem | 800 | 1.05 | -0.03em |
| `h1` | 2.25rem | 800 | 1.1 | -0.025em |
| `h2` | 1.5rem | 700 | 1.2 | -0.02em |
| `h3` | 1.125rem | 700 | 1.3 | -0.01em |
| `body` | 1rem | 400 | 1.6 | 0 |
| `bodySmall` | 0.875rem | 400 | 1.5 | 0.005em |
| `caption` | 0.75rem | 500 | 1.4 | 0.02em |
| `code` | 0.8125rem | 400 | 1.6 | 0 |

## Focus

Every interactive element shows a visible focus ring. There are **zero**
`focus-visible`, `:focus` or `outline` declarations in the frontend today, so
keyboard users navigate on the user-agent default or on nothing.

```
outline: 2px solid #2563EB;
outline-offset: 2px;
```

---

## Contrast floors

**4.5:1 for body text. 3:1 for large text (≥18.66px bold or ≥24px) and for
non-text UI boundaries.** WCAG 2.1 AA.

Every pair the product actually uses is declared in `PAIRS` in `tokens.ts` and
asserted by `test_every_declared_pair_meets_its_contrast_floor`. A pair that is
not declared cannot be built by the token API, because a foreground is only
reachable through the surface it sits on.

`test_the_spec_contrast_table_matches_computed_ratios` recomputes every ratio
published in this file and fails on a discrepancy over ±0.05 — so the table
above cannot rot the way the one it replaces did.

---

## Scope

This specification covers colour, type and focus. It is **not** a claim of WCAG
conformance: criterion F6 is contrast only. Screen-reader behaviour, live-region
announcements, skip links and full keyboard navigation beyond focus visibility
are not addressed here and must not be implied by citing it.
