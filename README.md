# Agent System — Design System

This is the design system for **Agent System**, a personal AI co-worker that runs on your VPS and is reachable from web, Telegram, and (eventually) mobile. The product wraps multi-model LLM routing, a $30/month enforced budget, persistent memory, and a tool-using agent behind a single dashboard.

> **Tagline shape:** *"Your personal co-worker that you control, own, and understand."*
> Not a Perplexity replacement. Not an enterprise SaaS. A self-hosted, cost-capped, model-agnostic agent for indie builders.

The aesthetic is **operations-deck** — dark glass panels, faint grid backgrounds, a single neon accent that glows on hover, and uppercase Orbitron lockups for headings. Information-dense but never cluttered. Always feels like you're piloting something.

---

## Source materials

Everything in this design system was derived from the public repo:

- **GitHub:** [`tbmobb813/agent-system`](https://github.com/tbmobb813/agent-system) (`main` branch)
  - Frontend (Next.js 15 + React 19 + Tailwind): `frontend/`
    - `frontend/app/globals.css` — full theme-token contract (4 themes)
    - `frontend/app/layout.tsx` — root font wiring (Orbitron + Space Grotesk via `next/font/google`)
    - `frontend/components/SiteNav.tsx`, `ThemeSwitcher.tsx`, `CostTracker.tsx`, `MarkdownContent.tsx`, `PageHeader.tsx`
    - `frontend/app/page.tsx` (Dashboard), `agent/page.tsx`, `commands/page.tsx`, `documents/page.tsx`
  - Marketing/voice copy: `README.md`, `START_HERE.md`, `EVERYTHING_YOU_GOT.md`, `QUICKSTART.md`, `PACKAGE_SUMMARY.md`
  - Backend reference (FastAPI + PydanticAI): `backend/app/`

The reader does not need access to that repo to use this design system — every artifact below is reproducible from the files in this folder.

---

## What's in this folder (manifest)

| Path | What it is |
| --- | --- |
| `README.md` | This file. Voice, visuals, iconography, manifest. |
| `colors_and_type.css` | All design tokens — themes, fonts, spacing, motion, panel styles. **Import this first.** |
| `SKILL.md` | Cross-compatible agent-skill front-matter for use in Claude Code. |
| `assets/` | Logos, badges, generic illustrations. Copy out, do not link cross-project. |
| `preview/` | Small HTML cards that populate the Design System review tab. Reference for what the system looks like assembled. |
| `ui_kits/dashboard/` | High-fidelity recreation of the Next.js dashboard product. `index.html` plus modular JSX components. |

---

## Index — start here

1. **Read `colors_and_type.css`** — it documents every token by example. The four themes (`neon-command`, `starforge`, `retro-grid`, `clean-tech`) all swap through the same variable contract.
2. **Browse `preview/`** — every card is a self-contained specimen, ~700 px wide. Use them as a swipe file when composing new screens.
3. **Open `ui_kits/dashboard/index.html`** — the canonical surface. If you're mocking a new page that lives inside this product, start here and remove what you don't need.
4. **For new artifacts (slides, prototypes, throwaway mocks):** import `colors_and_type.css`, set `data-theme="neon-command"` on `<html>`, add `class="atmosphere"` to `<body>`, and you have the look in three lines.

---

## Product surfaces

There is one product, accessible through several front doors:

| Surface | Purpose | Status in this kit |
| --- | --- | --- |
| **Web dashboard** (Next.js) | The "command center" — agent, history, costs, analytics, documents, settings, commands reference | ✅ Recreated in `ui_kits/dashboard/` |
| **Telegram bot** | Mobile-first one-line access (`/ask`, `/code`, `/status`) | Documented; no separate UI kit (chat-native) |
| **API / `/docs`** | FastAPI Swagger explorer | Out of scope (auto-generated) |
| **VPS CLI** (`agent`, `agent stop`, `agent logs`) | Local control plane | Documented in commands reference |

---

## Content fundamentals

The voice is **terse, direct, second-person, and slightly DIY**. It treats the reader as a competent operator who is here to ship, not to be sold to.

### Tone & posture

- **Second person, present tense.** "*Watch your agent think.*" "*Type a query, click Run.*" Never "users," never "we are pleased to."
- **Imperative for instructions.** "*Read `SETUP.md`.*" "*Add your `OPENROUTER_API_KEY`.*" Periods, not exclamation points (mostly).
- **Allowed enthusiasm:** the marketing docs use a measured number of emoji as section markers — 🚀, ✨, 💪 — and a closing rocket on big transitions. **The product UI itself uses zero emoji.** Treat emoji as for README and onboarding *only*.
- **First-person plural is rare** and only shows up in the philosophy section: "*This system was built with these principles*."
- **No marketing fluff.** Copy reads like a thoughtful README from a developer who respects your time. "Production-ready," "extensible," "you control" — earned, not sprinkled.

### Casing

- **Sentence case** for body, table cells, panel headings. ("This month by model," not "This Month By Model.")
- **Title Case** for page titles and major nav. ("Run Agent," "Recent Tasks," "Monthly Budget.")
- **UPPERCASE with letter-spacing** for eyebrow labels (`Command Center`, `Live session`, `Reference`), brand mark (`AI AGENT`), and tiny chips (`CORE`, `LOGS`, `COST`, `DATA`).
- **Lowercase** for state strings inside data tables: `completed`, `failed`, `running`, `stopped`, `ok`. Status is a value, not a sentence.

### Numbers and units

- Money: `$30`, `$0.0001`, `$1/MTok`. Always with the dollar sign, no spaces.
- Token costs: `$1/MTok` (per million tokens).
- Time: `m`, `h`, `d` ago — `5m ago`, `2h ago`, `3d ago` (`just now` for under a minute).
- Percentages: one decimal in budget contexts (`14.1%`), zero decimals in compact chips.

### Examples lifted directly

- Dashboard hero, dynamically generated: *"Telemetry, budget, and execution history in one live operations deck."*
- Documents page: *"Upload PDFs, DOCX, or text files. The agent searches them automatically when answering questions."*
- Commands page: *"CLI entrypoints, web routes, Telegram verbs, and API paths—filter the tables when you are looking for one string."*
- Budget alert tone: *"System stops making API calls and routes to local models or degrades gracefully."* — clinical, no panic.
- Empty states: *"No tasks yet"*, *"No usage this month"*, *"No documents yet. Upload one above."* — short, no apology.

### Phrases to keep using

- **command center**, **operations deck**, **live session**, **co-worker**, **enforced**, **routed**, **cap**, **degrades gracefully**, **persistent memory**, **multi-model routing**.

### Phrases to avoid

- "Welcome to…", "We're excited to…", "powerful", "seamless", "revolutionary", "next-generation", "AI-powered" (the whole product is AI; redundant).
- Don't say "the user" — say "you."

---

## Visual foundations

The whole system is one consistent visual idea: **frosted glass panels floating over a subtly atmospheric dark background, with a single neon accent that glows where the user can act.**

### Color

- **Four themes**, all using the same CSS-variable contract. `neon-command` (default, deep blue-black + teal), `starforge` (indigo + gold, warmer for analyst sessions), `retro-grid` (synthwave magenta + cyan), `clean-tech` (the sole light theme). See `colors_and_type.css` for the complete palettes.
- **One accent at a time.** Each theme picks `--accent` (primary action / brand) and `--accent-2` (links, secondary highlights). The two together define every glow, gradient, and chart color in the theme. Don't mix accents from different themes.
- **Status colors are theme-stable in spirit:** green for success, amber for warn, red for danger, the secondary blue for "running." The exact hex shifts per theme so the contrast stays right against that theme's surface.
- **Surfaces use translucency** (`rgba(13, 21, 32, 0.72)` for `--surface`) so the background atmosphere reads through. The light theme keeps translucency too — `rgba(255, 255, 255, 0.78)`.
- **Glows use an RGB-triplet token** (`--glow: 43 227 198`) consumed as `rgba(var(--glow), …)`. Always tied to `--accent` in spirit; never freestyle.

### Type

- **Display: Orbitron** — geometric, slightly futurist, looks like a control panel. 500 / 700 weights. Used for the brand mark, page titles via `.section-title`, and h1/h2.
- **Body: Space Grotesk** — humanist sans, 400 / 500 / 700. Wide x-height, very legible at small sizes. The default for everything that isn't display or mono.
- **Mono: JetBrains Mono** — code, model identifiers (`claude-3.5-haiku`), command tokens. The product also styles these in `--accent-2` with a soft surface background.
- **Tracking is intentional.** Eyebrows: `0.22em`. Brand: `0.08em`. Section titles: `0.06em`. Pills/chips: `0.18em`. Body: default.
- **No font weight below 400.** No italics in UI — italics only inside markdown blockquotes.

### Backgrounds

- **Atmosphere is two radial washes + a faint grid + a vertical fade.** Top-left wash uses the theme's accent at 18% opacity, top-right uses accent-2 mixed with transparent, base is `--bg` fading toward black. This stays fixed (`background-attachment: fixed`) so it doesn't scroll.
- **The grid is masked with a radial fade** so it disappears at the edges of the viewport. 36×36 px lines, 3% white. It reads as texture, not as a chart.
- **No hand-drawn illustrations. No photography. No gradients on UI elements** beyond the budget-bar fill (chart-primary → chart-secondary) and the accent button (`--accent` → mixed `--accent-2`).
- The light theme keeps the same atmosphere with washes pulled from its own accent — it lands as "clean" rather than dark, but the structure is identical.

### Animation

- **Fast, additive, springless.** `--dur-quick` 150ms for hover. `--dur-base` 180ms for general transitions. `--dur-slow` 420ms for the `fade-up` mount animation, which only translates Y by 8px and fades in.
- **Hover effect is always two things:** color/border shift to the accent, and a subtle `translateY(-1px)` + glow shadow. Never scale.
- **Press effect is `translateY(0)`** — collapses the lift back. Sometimes paired with a brief opacity bump.
- **No bouncy easing, no springs, no parallax, no scroll-jacking.** The `data-motion="minimal"` profile collapses everything to 1ms for accessibility.
- **Easing:** `cubic-bezier(0.22, 1, 0.36, 1)` (`--ease-out`) is the workhorse.

### Borders, radii, shadows

- **Default panel radius:** `0.95rem` (15.2 px). Compact density: `0.75rem`. Buttons / chips / inputs: `0.5–0.75rem`. Pills (chips, progress bars): `999px`.
- **Borders are 1 px,** color = `--border` which is the theme's mid-tone at ~25% opacity. Always present on panels and inputs; never doubled.
- **Shadows always pair an inner highlight with an outer drop:**
  ```
  inset 0 0 0 1px rgba(255, 255, 255, 0.02),  /* fake light from above */
  0 12px 40px rgba(0, 0, 0, 0.24);            /* lift off the bg */
  ```
- **Glow shadow is hover-only,** uses the theme's `--glow` triplet at 20–50% opacity. `0 10px 24px rgba(var(--glow), 0.20)` is the standard.
- **No drop shadows on text** except the brand title and active nav links, which get a small text-shadow glow.

### Transparency and blur

- **Panels: `backdrop-filter: blur(12px)`** + 64–78% opacity backgrounds. The blur is what makes the glass look right.
- **App shell: `blur(14px)`** with a slightly darker tint so it sits on top of content without disappearing.
- **Use blur sparingly elsewhere.** Never on full-page modals (they should be solid). Never on hover states.

### Layout rules

- **Max content width: 6xl (72rem / 1152 px)** centered, with `px-4` (16 px) horizontal gutters that grow to `px-6` on larger panels. The dashboard, all pages, and the nav use this same column.
- **Vertical rhythm:** `space-y-6` between major sections, `space-y-2` inside lists.
- **Sticky nav** at the top of every page. No footer chrome — the dashboard is the home, not a marketing site.
- **Two-column on desktop, one-column on mobile.** Grid breaks at `sm:` (640 px) for stat cards, `lg:` (1024 px) for split-panel layouts.

### Cards / panels in use

A panel = `1 px border @ 26% opacity → 0.95rem radius → translucent surface → backdrop blur → inset highlight + outer drop`. Inside, the typical sequence is:

1. Optional eyebrow (uppercase, tracked, muted)
2. Title (`section-title`, display font)
3. Body (Space Grotesk, default leading)
4. Action row (right-aligned `btn-ghost` + `btn-accent`, or a single link in `--accent-2`)

Insert dividers as `border-b border-[color:var(--border)]` between rows of a list panel — never a `<hr>`.

### Imagery vibe

- **Cool when dark, neutral when light.** Photography (if introduced later) should be high-contrast night-shot, faintly desaturated, with cyan/blue cast — never warm orange.
- **No grain, no film effects, no people.**
- The product itself doesn't ship imagery yet — the "art" is the UI: glow, panels, type. Treat that as the brand.

---

## Iconography

The Agent System repo **does not ship a custom icon set**. The dashboard uses two strategies, and you should follow them in this order:

### 1. Tracked-uppercase text chips (the dominant motif)

Most "icon slots" in the app are **3- to 4-letter uppercase chips** — `CORE`, `LOGS`, `COST`, `DATA`, `DOCS`, `CONF`, `CMD`. They're rendered as `.eyebrow`-style pills sitting in `--surface-soft` with a `--border` outline. This is the brand's signature: text-as-icon, no glyph required.

```html
<span class="chip">CORE</span>
```

Use these whenever you need to label a section, status, or nav target. They scale better than icons, are themable for free, and match the operations-deck personality.

### 2. Lucide via CDN — when you genuinely need a glyph

For the rare cases where text-chips don't work (toolbar buttons in dense UI, inline indicators in chat messages, document-type icons), **fall back to [Lucide](https://lucide.dev) loaded from CDN**. Stroke-based, 1.5–2 px stroke weight, single color, sized 16–20 px in nav and 12–14 px inline. Color the stroke with `currentColor` so it inherits the surrounding text color and adapts to theme.

```html
<!-- example: a "play" icon for the Run Agent button -->
<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <polygon points="5 3 19 12 5 21 5 3"/>
</svg>
```

> **Substitution flag:** the upstream repo does not pin a specific icon set (no `lucide-react` or `@radix-ui/icons` dependency in `frontend/package.json`). Lucide is the closest match to the existing visual weight (thin strokes, geometric, no fill). If the team standardizes on a different set later, swap the CDN — the rest of the system doesn't depend on it.

### 3. Emoji — README only, never in product UI

Emoji appear in the docs (🤖 ✨ 💪 🚀 ✅) as section anchors and tone markers. **They never appear in the rendered product.** When designing UI, treat emoji as out-of-bounds.

### 4. Unicode glyphs — light usage

The app uses a few Unicode arrows in nav links — `→` after "View all" and "Details" — and the budget UI uses `·` (middle dot) as a separator. Both are fine. Avoid heavier Unicode (★, ✓, ⚠, ●) — for those, use the appropriate Lucide glyph.

### 5. The "logo"

There is no logotype-as-image in the upstream repo. The brand mark is **a CSS class:** `.brand-title` rendering the text **`AI AGENT`** in Orbitron, uppercase, `--accent` color, with a glow text-shadow. We provide an SVG/PNG version in `assets/` for cases where text rendering isn't an option (favicons, OG images, decks).

---

## Quick start for a new artifact

```html
<!doctype html>
<html lang="en" data-theme="neon-command" data-density="comfortable" data-motion="cinematic">
  <head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="colors_and_type.css">
    <title>My Mock</title>
  </head>
  <body class="atmosphere">
    <div style="max-width: 72rem; margin: 0 auto; padding: 2rem 1rem;">
      <p class="eyebrow">Command center</p>
      <h1 class="section-title">Hello, operator</h1>

      <div class="panel" style="padding: 1.5rem; margin-top: 1.5rem;">
        Panel content goes here.
      </div>
    </div>
  </body>
</html>
```

That's the whole brand in 15 lines. From there, lift components out of `ui_kits/dashboard/` and you're done.

---

## Caveats / known gaps

- **No icon set is shipped** — Lucide-via-CDN is a substitution. Confirm with the team if you want to standardize.
- **No real logo file** in the upstream repo — `assets/logo-mark.svg` is reconstructed from the CSS brand mark.
- **No marketing-site surface** — the Next.js app is the product, not a landing page. If a landing page is added later, the visual rules here all apply unchanged.
