# Projects & Business Context

## Owner

**JNix** — solo operator running multiple development projects, content brands, and business ventures simultaneously. Technical background spans mobile (Flutter, React Native), desktop (C#/WPF), systems (C, WSL2), Python scripting, and web. GitHub: tbmobb813.

---

## Development Projects

### ReGrabber
Social media repost app for mobile.
- **Stack:** Flutter/Dart, FFmpeg, Firebase, AdMob
- **Status:** Active — core download service built; in-progress: auto-open toggle, OpenFile support for iOS, Android 14 permission handler testing
- **Notes:** Revenue model via AdMob. Modular service architecture.

### GameTranslationTool
WPF desktop app for game ISO extraction and text translation.
- **Stack:** C#, WPF, Serilog, MSAL (Azure auth), Azure Cognitive Services Translation API
- **Status:** Active
- **Notes:** Windows-only. Uses IGDB API for game metadata lookups — this logic can be reused in other game-related tooling.

### NixCategories
PSP plugin and INI category manager.
- **Stack:** C, WSL2 toolchain, Eboot parser
- **Status:** Active
- **Notes:** Low-level systems work. PSP homebrew ecosystem.

### KidMap
Gamified navigation and mapping app for kids.
- **Stack:** React Native, MapLibre, Firebase
- **Status:** In development
- **Notes:** Safety-first design. Child-appropriate UI. Location features need careful permission handling.

---

## Content Brands

### TechTrendWire
Tech news and analysis publication.
- **Platforms:** WordPress (primary), YouTube, Pinterest
- **Tone:** Analytical, insightful, accessible tech journalism — not hype-driven
- **Topics:** AI, Gaming, VR/AR, Hardware, Tech Trends
- **Goals:** Traffic growth, SEO optimization, affiliate readiness
- **Content format:** Articles need SEO keywords, meta description, and CTA. Suggest video + article crossovers when relevant.

### MindType.Studio
Emotional wellness visual brand.
- **Platforms:** Instagram (primary), Notion (planning), Canva (design)
- **Tone:** Poetic, emotional minimalism — evoke introspection, not advice
- **Visuals:** Black background, serif typography, subtle fades
- **Content series:** "Feelings vs Emotions" — carousels, quotes, reels, prompts
- **Frequency:** 3 posts/week: carousel + quote + story
- **Format ideas:** "visual moodboards" or "emotional scripts"

---

## Business Ventures

### NixLevel (Etsy + Printify)
Print-on-demand apparel store.
- **Platforms:** Etsy storefront, Printify for fulfillment
- **Tasks:** Product templates, variant naming, product descriptions, tag sets, mockup suggestions, lifestyle photo angles, profit margin tracking, Printify cost monitoring

### Courier / Delivery Startup
Local delivery service (weekend focus).
- **Vehicle:** Cargo van or rented vehicle
- **Tools:** Google Sheets (recordkeeping), Notion (planning)
- **Needs:** Route templates, pricing strategy, startup cost tracking, client outreach templates, funding tracking

---

## Preferred Tech Stack (cross-project)

- Flutter/Dart — mobile
- C#/WPF — Windows desktop
- Python — scripting and automation
- React Native — cross-platform mobile (KidMap)
- GitHub — version control (main/dev branch model)
- Google Sheets / Notion — business operations and planning

---

## Cross-Project Notes

- IGDB API logic from GameTranslationTool can be reused in any game-related project (NixCategories, future tools).
- Firebase setup (auth, Firestore, storage) is shared knowledge between ReGrabber and KidMap.
- When a task in one project overlaps another (e.g., API patterns, state management), call it out and suggest reuse.
- Budget constraint: $30/month hard cap on AI API spend across all work.
