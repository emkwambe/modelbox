# ModelBox AI: Brand Design System
## Visual Identity, Color, Typography, and Application Guidelines

**Version:** 1.0  
**Date:** August 2026  
**Purpose:** Establish a cohesive, authoritative, and modern visual identity for ModelBox AI that communicates precision, intelligence, and trust — the three pillars of AI-powered data modeling.

---

## 1. Brand Positioning & Personality

### Brand Essence
**ModelBox AI transforms how data teams design, modernize, and govern their databases through AI-powered schema synthesis, reverse engineering, and contract governance.**

### Brand Personality

| Trait | Expression | Avoid |
|-------|-----------|-------|
| **Precise** | Exact specifications, clean lines, mathematical confidence | Vague, fluffy, imprecise language |
| **Intelligent** | AI-native, forward-thinking, solves complex problems | Gimmicky, overly playful, childish |
| **Trustworthy** | Enterprise-ready, secure, governed | Cheap, untested, risky |
| **Modern** | Cloud-native, code-first, dbt-aligned | Legacy, outdated, on-premise aesthetic |
| **Empowering** | Amplifies engineers, reduces toil, accelerates careers | Replaces humans, eliminates jobs |

### Brand Voice
- **Confident but not arrogant.** We know data modeling deeply, but we respect the practitioner's expertise.
- **Technical but accessible.** We speak to engineers in their language, but we do not gatekeep.
- **Forward-looking but grounded.** We talk about the future of AI-native modeling, but we deliver production-ready tools today.

---

## 2. Logo System

### Primary Logo: The ModelBox Mark

**Concept:** The intersection of "model" (structure, schema, grid) and "box" (container, package, deliverable) — fused with an AI-native signal.

**Design Rationale:**
- The mark is built on a **4x4 grid** — representing the structured, dimensional nature of data modeling (tables, rows, columns, relationships).
- One cell is **differentiated** — representing the AI that sees patterns humans miss, the "spot the flaw" insight, the single source of truth.
- The mark is **geometric, not organic** — precision over decoration.
- The mark is **monochrome-capable** — works in any color, any background, any size.

**Logo Construction:**

```
GRID CONSTRUCTION (4x4)

┌───┬───┬───┬───┐
│   │   │   │   │  ← Row 1: Uniform
├───┼───┼───┼───┤
│   │ ■ │   │   │  ← Row 2: The "AI Signal" — one cell elevated
├───┼───┼───┼───┤
│   │   │   │   │  ← Row 3: Uniform
├───┼───┼───┼───┤
│   │   │   │   │  ← Row 4: Uniform
└───┴───┴───┴───┘

The elevated cell (■) represents:
- The AI insight that spots the flaw
- The primary key that unlocks the relationship
- The single source of truth in a sea of data
```

**Logo Variants:**

| Variant | Usage | Specifications |
|---------|-------|---------------|
| **Primary (Horizontal)** | Website header, presentations, email signatures | Mark left + wordmark right. Minimum width: 120px |
| **Stacked** | Social media avatars, app icons, square spaces | Mark above wordmark. Minimum size: 40px |
| **Mark Only** | Favicons, small UI elements, watermarks | Minimum size: 16px. Always maintain proportions |
| **Wordmark Only** | Long-form content where mark is redundant | "ModelBox" in brand typeface + "AI" in accent weight |
| **Monochrome** | Single-color applications (print, embossing, stamps) | All elements in one color. No gradients |

**Clear Space:**
- Minimum clear space around the logo = height of the "M" in ModelBox
- Never place the logo closer than this distance to other elements, page edges, or images

**Minimum Sizes:**
- Digital: 40px wide (stacked), 120px wide (horizontal)
- Print: 15mm wide (stacked), 45mm wide (horizontal)

**Incorrect Usage (Never):**
- Do not stretch, skew, or rotate the logo
- Do not change the logo colors outside the approved palette
- Do not add effects (shadows, glows, bevels, 3D)
- Do not place the logo on busy backgrounds without sufficient contrast
- Do not separate the mark from the wordmark in the primary variant

---

## 3. Color Palette

### Primary Colors

The primary palette communicates **precision, trust, and intelligence**.

| Color Name | Hex | RGB | CMYK | Usage |
|-----------|-----|-----|------|-------|
| **ModelBox Navy** | `#0A1628` | 10, 22, 40 | 75, 45, 0, 84 | Primary background, headers, depth |
| **ModelBox Blue** | `#2563EB` | 37, 99, 235 | 84, 58, 0, 8 | Primary brand color, CTAs, links, logo mark |
| **ModelBox Cyan** | `#06B6D4` | 6, 182, 212 | 97, 14, 0, 17 | AI signal, highlights, data flow, accents |

### Secondary Colors

The secondary palette provides **warmth, energy, and differentiation**.

| Color Name | Hex | RGB | CMYK | Usage |
|-----------|-----|-----|------|-------|
| **ModelBox Amber** | `#F59E0B` | 245, 158, 11 | 0, 35, 96, 4 | Warnings, alerts, attention, secondary CTAs |
| **ModelBox Emerald** | `#10B981` | 16, 185, 129 | 91, 0, 30, 27 | Success, validation, quality checks, pass states |
| **ModelBox Rose** | `#F43F5E` | 244, 63, 94 | 0, 74, 61, 4 | Errors, breaking changes, failures, critical alerts |

### Neutral Colors

The neutral palette provides **structure, hierarchy, and readability**.

| Color Name | Hex | RGB | Usage |
|-----------|-----|-----|-------|
| **Neutral 50** | `#F8FAFC` | 248, 250, 252 | Page backgrounds, cards |
| **Neutral 100** | `#F1F5F9` | 241, 245, 249 | Subtle backgrounds, hover states |
| **Neutral 200** | `#E2E8F0` | 226, 232, 240 | Borders, dividers, separators |
| **Neutral 300** | `#CBD5E1` | 203, 213, 225 | Disabled states, placeholder text |
| **Neutral 400** | `#94A3B8` | 148, 163, 184 | Secondary text, metadata |
| **Neutral 500** | `#64748B` | 100, 116, 139 | Tertiary text, captions |
| **Neutral 600** | `#475569` | 71, 85, 105 | Body text on light backgrounds |
| **Neutral 700** | `#334155` | 51, 65, 85 | Headings on light backgrounds |
| **Neutral 800** | `#1E293B` | 30, 41, 59 | Strong headings, dark UI elements |
| **Neutral 900** | `#0F172A` | 15, 23, 42 | Deepest dark, near-black |

### Semantic Color Mapping (Product UI)

| State | Color | Usage in ModelBox AI |
|-------|-------|---------------------|
| **Primary Action** | ModelBox Blue `#2563EB` | Generate schema, Deploy, Save |
| **AI/Insight** | ModelBox Cyan `#06B6D4` | AI suggestions, auto-detect, highlights |
| **Success** | ModelBox Emerald `#10B981` | Test passed, validation green, contract approved |
| **Warning** | ModelBox Amber `#F59E0B` | Breaking change alert, deprecation notice |
| **Error** | ModelBox Rose `#F43F5E` | Test failed, schema conflict, critical issue |
| **Info** | ModelBox Blue `#2563EB` | Tips, documentation links, help |

### Gradient Usage

**Primary Gradient (Hero Backgrounds):**
```css
background: linear-gradient(135deg, #0A1628 0%, #1E293B 50%, #0F172A 100%);
```

**AI Signal Gradient (Accent Elements):**
```css
background: linear-gradient(135deg, #2563EB 0%, #06B6D4 100%);
```

**Glow Effect (AI Highlights):**
```css
box-shadow: 0 0 20px rgba(6, 182, 212, 0.3);
```

---

## 4. Typography System

### Primary Typeface: Inter

**Why Inter:** Designed for screen readability, excellent at small sizes, neutral and professional, widely available (Google Fonts), engineered for UI — perfect for a tool built by engineers, for engineers.

**Fallback Stack:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`

### Type Scale

| Token | Size | Weight | Line Height | Letter Spacing | Usage |
|-------|------|--------|-------------|----------------|-------|
| **Display** | 64px / 4rem | 800 | 1.1 | -0.02em | Hero headlines, landing page H1 |
| **H1** | 48px / 3rem | 700 | 1.15 | -0.02em | Page titles, major section headers |
| **H2** | 36px / 2.25rem | 700 | 1.2 | -0.01em | Section headers, blog post titles |
| **H3** | 28px / 1.75rem | 600 | 1.25 | -0.01em | Subsection headers, card titles |
| **H4** | 24px / 1.5rem | 600 | 1.3 | 0em | Feature titles, modal headers |
| **H5** | 20px / 1.25rem | 600 | 1.35 | 0em | Small headers, sidebar titles |
| **H6** | 16px / 1rem | 600 | 1.4 | 0.01em | Labels, metadata headers |
| **Body Large** | 18px / 1.125rem | 400 | 1.6 | 0em | Lead paragraphs, introductions |
| **Body** | 16px / 1rem | 400 | 1.6 | 0em | Standard body text |
| **Body Small** | 14px / 0.875rem | 400 | 1.5 | 0.01em | Secondary text, descriptions |
| **Caption** | 12px / 0.75rem | 500 | 1.4 | 0.02em | Labels, timestamps, metadata |
| **Code** | 14px / 0.875rem | 400 | 1.6 | 0em | Inline code, technical specifications |
| **Code Block** | 13px / 0.8125rem | 400 | 1.7 | 0em | Multi-line code, YAML, SQL |

### Monospace Typeface: JetBrains Mono

**Why JetBrains Mono:** Designed specifically for code, increased letter height for readability, ligatures for common programming symbols, distinguishes similar characters (0/O, l/I/1).

**Usage:** All code elements, CLI examples, schema definitions, data contracts, terminal output.

**Fallback Stack:** `'JetBrains Mono', 'Fira Code', 'SF Mono', 'Consolas', monospace`

---

## 5. Visual Language

### Shapes & Geometry

| Element | Style | Rationale |
|---------|-------|-----------|
| **Cards** | 8px border radius | Modern but not playful; approachable precision |
| **Buttons** | 6px border radius | Slightly tighter than cards; action-oriented |
| **Inputs** | 4px border radius | Minimal; keeps focus on content |
| **Avatars** | 50% border radius (circular) | Human element; breaks the grid |
| **Tags/Badges** | 4px border radius | Compact, readable |
| **Modals** | 12px border radius | Elevated, distinct from background |
| **Dividers** | 1px solid Neutral-200 | Subtle separation without visual weight |

### Grid System

**Base Unit:** 4px  
**Column Grid:** 12-column  
**Gutter:** 24px (desktop), 16px (tablet), 12px (mobile)  
**Max Content Width:** 1280px  
**Side Padding:** 48px (desktop), 24px (tablet), 16px (mobile)

### Shadows & Elevation

| Level | Shadow | Usage |
|-------|--------|-------|
| **Flat** | none | Cards on light backgrounds, primary content |
| **Raised** | `0 1px 3px rgba(15, 23, 42, 0.08)` | Hover states, subtle elevation |
| **Elevated** | `0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.06)` | Cards, dropdowns, popovers |
| **Floating** | `0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.06)` | Modals, toasts, notifications |
| **AI Glow** | `0 0 20px rgba(6, 182, 212, 0.25)` | AI-generated elements, highlights, suggestions |

### Patterns & Textures

**Grid Pattern (Subtle Background):**
```css
background-image: 
  linear-gradient(rgba(37, 99, 235, 0.03) 1px, transparent 1px),
  linear-gradient(90deg, rgba(37, 99, 235, 0.03) 1px, transparent 1px);
background-size: 40px 40px;
```
Used on: Hero sections, product UI backgrounds, technical documentation.

**Dot Pattern (Data Density):**
```css
background-image: radial-gradient(circle, rgba(6, 182, 212, 0.15) 1px, transparent 1px);
background-size: 24px 24px;
```
Used on: Feature sections, statistics backgrounds, "data mesh" visualizations.

---

## 6. Imagery & Iconography

### Photography Style

**When photography is used (team, events, customers):**
- **Treatment:** Desaturated, cool-toned, high contrast
- **Color grade:** Push toward blue/cyan shadows, neutral highlights
- **Subject matter:** Engineers at work, architectural details, abstract data visualizations
- **Avoid:** Stock photos of generic "business people shaking hands," overly staged scenes, warm/saturated colors

### Illustration Style

**When illustrations are used (product features, concepts):**
- **Style:** Geometric, isometric, line-art with solid fills
- **Color:** Limited to brand palette; ModelBox Blue and Cyan as primary accents
- **Subject:** Abstract representations of data structures (nodes, connections, schemas, tables)
- **Avoid:** Cartoonish characters, organic/freehand styles, gradients in illustrations

### Iconography

**Icon Set:** Phosphor Icons or Heroicons (outline style)
**Size Scale:** 16px, 20px, 24px, 32px, 48px
**Stroke Width:** 1.5px (default), 2px (emphasis)
**Color:** Inherit from text color or use semantic colors

**Key Icons for ModelBox AI:**
- Schema/Grid icon (primary product metaphor)
- AI/Sparkle icon (AI capabilities)
- Shield/Check icon (governance, quality)
- GitBranch icon (version control, lineage)
- ArrowsLeftRight icon (diffing, migration)
- Database icon (data sources)
- Code icon (dbt, SQL output)

---

## 7. Application Guidelines

### Website

**Homepage Hero:**
- Background: ModelBox Navy with grid pattern
- Headline: Display size, white, "AI-Powered Schema Design for Modern Data Teams"
- Subheadline: Body Large, Neutral-300, "Generate production-ready data models, dbt projects, and data contracts from natural language requirements."
- CTA Button: ModelBox Blue background, white text, 6px radius, "Start Building Free"
- Secondary CTA: Transparent with white border, "View Documentation"
- Visual: Abstract 3D schema visualization or animated grid with AI signal

**Product UI:**
- Sidebar: Neutral-900 background, Neutral-400 text, Cyan accent for active state
- Main Canvas: Neutral-50 background, white cards with Elevated shadow
- Schema Elements: Neutral-800 borders, Blue headers, Cyan for AI-generated fields
- Code Panels: Neutral-900 background, JetBrains Mono, syntax-highlighted
- Status Indicators: Emerald (pass), Amber (warning), Rose (error), Blue (info)

### LinkedIn

**Profile Banner:**
- Dimensions: 1584 x 396px
- Background: ModelBox Navy with subtle grid pattern
- Content: Logo mark (left), tagline (center-right), Cyan accent line
- Tagline: "AI-Powered Data Modeling"

**Post Images:**
- Dimensions: 1200 x 627px (landscape), 1080 x 1080px (square)
- Background: Neutral-50 or ModelBox Navy
- Typography: Inter, H3 size for headlines
- Accent: ModelBox Cyan for highlights, data points, or AI signal elements
- Border radius: 8px if showing UI mockups

**Document Carousels (PDF):**
- Page size: 1080 x 1350px (4:5 ratio)
- Background: Neutral-50 or gradient (Navy to Neutral-900)
- Typography: Inter, H2 for page titles, Body for content
- Accent: Cyan for data points, Blue for structure, Emerald for success metrics

### Email

**Header:**
- Background: ModelBox Navy
- Logo: White monochrome mark + wordmark, centered
- Height: 80px

**Body:**
- Background: Neutral-50
- Text: Neutral-700 (headings), Neutral-600 (body)
- Links: ModelBox Blue, underline on hover
- Buttons: ModelBox Blue, white text, 6px radius, full-width on mobile

**Footer:**
- Background: Neutral-100
- Text: Neutral-500, Caption size
- Social icons: Neutral-400, hover to Blue

### Presentations

**Title Slide:**
- Background: ModelBox Navy with grid pattern
- Title: Display size, white, centered
- Subtitle: Body Large, Neutral-300
- Logo: White monochrome, bottom center

**Content Slides:**
- Background: Neutral-50
- Title: H2, Neutral-800, top-left
- Body: Body, Neutral-600
- Accent: Cyan for data callouts, Blue for structure diagrams
- Code blocks: Neutral-900 background, JetBrains Mono, 4px radius

**Closing Slide:**
- Background: Gradient (Navy to Neutral-900)
- CTA: "Try ModelBox AI" in Display size, white
- URL: Body Large, Cyan
- Logo: White monochrome, bottom

---

## 8. Brand in Action: Sample Compositions

### Composition A: LinkedIn Post (Authority)

```
[Image: 1200 x 627px]
Background: ModelBox Navy (#0A1628)
Grid pattern: Subtle, 40px grid, 3% opacity Blue

Left side (60%):
  Headline: "The State of Data Modeling 2026"
  Font: Inter, H2, white

  Subheadline: "200+ job postings analyzed"
  Font: Inter, Body, Neutral-300

  Stat callout: "72% of data engineers now write data models"
  Font: Inter, H3, Cyan (#06B6D4)

Right side (40%):
  Abstract schema visualization
  Nodes: Blue circles, 8px
  Connections: Cyan lines, 1px
  Background glow: Cyan, 10% opacity

Bottom:
  Logo: White monochrome mark + wordmark, left-aligned
  URL: modelbox.ai, Cyan, right-aligned
```

### Composition B: Product Screenshot (UI)

```
[Browser window mockup]
Background: Neutral-50 (#F8FAFC)

Sidebar (left, 240px):
  Background: Neutral-900 (#0F172A)
  Logo: White mark, top
  Nav items: Neutral-400, Cyan for active

Main Canvas (center, fluid):
  Card: White, Elevated shadow, 8px radius
  Schema diagram:
    - Tables: Neutral-800 border, white fill
    - Headers: Blue background, white text
    - AI-generated fields: Cyan left border, Cyan text
    - Relationships: Cyan dashed lines

  Code panel (bottom):
    Background: Neutral-900
    Font: JetBrains Mono, 13px
    Syntax highlighting: Blue (keywords), Cyan (strings), Emerald (comments)

Right Panel (320px):
  Background: Neutral-100
  Properties: Body Small, Neutral-600
  AI Suggestions: Cyan accent, sparkle icon
```

### Composition C: Event Booth / Swag

```
[Backdrop: 10ft x 8ft]
Background: ModelBox Navy
Grid pattern: Large, 80px, 5% opacity Cyan

Center:
  Logo: Primary horizontal, white, 3ft wide
  Tagline: "AI-Powered Schema Design" — Inter, H2, Cyan

Bottom third:
  Product screenshot: Floating on Elevated shadow
  CTA: "Try It Free" — Blue button, white text

[Swag: Stickers]
2x2 inch square
Background: White
Mark: ModelBox Blue, centered
Clear space: 4mm all sides

[Swag: T-Shirt]
Color: Navy or Black
Print: White mark (chest, 3 inch) + Cyan tagline (back, "ModelBox AI")
```

---

## 9. Accessibility Standards

### Color Contrast

| Combination | Ratio | WCAG Level |
|-------------|-------|------------|
| White on ModelBox Navy | 15.2:1 | AAA |
| White on ModelBox Blue | 4.8:1 | AA |
| Neutral-900 on Neutral-50 | 15.8:1 | AAA |
| Neutral-700 on Neutral-50 | 7.2:1 | AAA |
| ModelBox Blue on Neutral-50 | 5.1:1 | AA |
| ModelBox Cyan on ModelBox Navy | 7.8:1 | AAA |
| ModelBox Emerald on Neutral-900 | 6.4:1 | AA |
| ModelBox Amber on Neutral-900 | 7.1:1 | AAA |
| ModelBox Rose on White | 5.3:1 | AA |

**Minimum contrast for UI text:** 4.5:1 (AA) for body, 3:1 (AA Large) for headlines.

### Motion & Animation

- **Respect prefers-reduced-motion:** All animations must have a static fallback
- **Duration:** 200–300ms for micro-interactions, 400–600ms for page transitions
- **Easing:** `cubic-bezier(0.4, 0, 0.2, 1)` for standard, `cubic-bezier(0, 0, 0.2, 1)` for deceleration
- **AI signal animations:** Subtle pulse (opacity 0.5 → 1, 2s loop), never flashing or rapid

### Focus States

- **Outline:** 2px solid ModelBox Cyan, 2px offset
- **Visible on:** All interactive elements (buttons, links, inputs, cards)
- **Keyboard navigation:** Logical tab order, visible focus indicators

---

## 10. Brand Asset Checklist

### Immediate (Week 1–2)
- [ ] Primary logo (horizontal, SVG + PNG)
- [ ] Stacked logo (SVG + PNG)
- [ ] Mark only (SVG + PNG)
- [ ] Wordmark only (SVG + PNG)
- [ ] Monochrome variants (white, black, Navy)
- [ ] Favicon set (16px, 32px, 180px Apple touch)
- [ ] Social media avatars (LinkedIn, Twitter/X, GitHub)

### Short-term (Week 3–4)
- [ ] LinkedIn banner (1584 x 396px)
- [ ] Twitter/X header (1500 x 500px)
- [ ] Email header template
- [ ] Presentation template (Google Slides / PowerPoint)
- [ ] Business card design
- [ ] Letterhead template

### Medium-term (Month 2)
- [ ] Product UI style guide (Figma library)
- [ ] Icon set (custom + Phosphor curation)
- [ ] Illustration library (isometric data structures)
- [ ] Photography guidelines + sample treatment
- [ ] Swag designs (stickers, t-shirts, notebooks)
- [ ] Event booth design

### Ongoing
- [ ] Blog post image templates (3 variants)
- [ ] LinkedIn document templates (5 layouts)
- [ ] Webinar slide deck template
- [ ] Case study PDF template
- [ ] White paper template
- [ ] Video intro/outro animations

---

*Brand Design System v1.0 for ModelBox AI. All specifications are living documents and will evolve with the product and market.*
