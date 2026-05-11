---
name: agent-system-design
description: Use this skill to generate well-branded interfaces and assets for Agent_System, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

# Agent_System Design Skill

This skill packages the Agent_System design system: a dark-by-default
"operations deck" aesthetic for a personal AI agent platform.

## How to use this skill

1. **Read `README.md`** in this skill's root. It contains the full content
   fundamentals, visual foundations, color/type/spacing/motion tokens, and
   the iconography rules.
2. **Browse the other files** before designing. Notable ones:
   - `colors_and_type.css` — base + semantic CSS variables (`--accent`,
     `--surface`, `--font-display`, `h1`/`h2`/`code` selectors). Drop into
     any HTML file with `<link rel="stylesheet" href="colors_and_type.css">`.
   - `fonts/` — Orbitron, Space Grotesk, JetBrains Mono. Self-host these,
     don't reach for Google Fonts.
   - `assets/` — brand glyph SVG, atmosphere background, icon font reference.
     **Always copy assets from here.** Never draw your own SVG icons.
   - `ui_kits/dashboard/` — fully-built React kit. The smallest reusable
     pieces (`Panel`, `Eyebrow`, `ButtonAccent`, `Chip`, `Code`, `StatusDot`)
     are in `Components.jsx` — lift them directly.
   - `preview/` — small specimen cards, useful as references when you're
     unsure how a token reads in context.
3. **If creating visual artifacts** (slides, mocks, throwaway prototypes):
   copy assets out and create static HTML files for the user to view. Always
   start from `colors_and_type.css` plus the `<body class="atmosphere">`
   pattern; never hand-roll the gradient/grid background.
4. **If working on production code**: copy assets and read the rules here to
   become an expert in designing with this brand. The `app/globals.css` in the
   live Next.js dashboard is the source of truth — this skill mirrors it.

## When invoked without other guidance

Ask the user what they want to build or design, ask some questions, and act as
an expert designer who outputs HTML artifacts _or_ production code, depending
on the need. Useful prompts:

- Is this a new screen for the dashboard, a one-off mock, a slide for a deck,
  or a marketing page?
- Which palette — Neon Command (default, dark), Starforge (indigo + gold),
  Retro Grid (synthwave), or Clean Tech (the only light theme)?
- Density — comfortable (default) or compact?

## Non-negotiables

- **Do not invent new colors.** Use the four palettes in `colors_and_type.css`.
  If you genuinely need a new accent for a one-off, derive it with `oklch`
  from an existing token rather than picking a fresh hex.
- **Do not draw new icons.** This product uses text-as-icon conventions
  (`CORE`/`LOGS`/`COST`/`DATA` etched chips) plus Lucide via CDN for
  functional glyphs. If you can't find what you need in either, ask the user.
- **Do not use emoji.** They break the operations-deck tone.
- **Sentence-case copy.** Direct, second-person, light technical jargon.
  Numbers carry the meaning; keep adjectives out.
- **Springless motion.** 150–420 ms, `cubic-bezier(.22, 1, .36, 1)`. No
  bounces, no overshoots. Hover lifts 1px and gains a teal glow shadow; that's
  it.
